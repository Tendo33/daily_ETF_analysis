from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_market_review(
    report_rows: list[dict[str, Any]],
    *,
    industry_map: dict[str, list[str]] | None = None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
    trend_window_days: int = 5,
    risk_top_n: int = 3,
    recommend_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = _normalize_weights(recommend_weights)
    if not report_rows:
        return {
            "total": 0,
            "avg_score": None,
            "trend_counts": {},
            "action_counts": {},
            "top": [],
            "bottom": [],
            "risk_alerts": [],
            "industry": [],
        }

    scores = [row.get("score") for row in report_rows]
    numeric_scores = [float(s) for s in scores if isinstance(s, int | float)]
    avg_score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else None

    trend_counts = Counter(
        str(row.get("trend", "unknown")).lower() for row in report_rows
    )
    action_counts = Counter(
        str(row.get("action", "unknown")).lower() for row in report_rows
    )

    sorted_rows = sorted(
        report_rows, key=lambda item: _safe_score(item.get("score")), reverse=True
    )
    top = [
        {
            "symbol": row.get("symbol"),
            "score": row.get("score"),
            "trend": row.get("trend"),
            "action": row.get("action"),
        }
        for row in sorted_rows[:5]
    ]
    bottom = [
        {
            "symbol": row.get("symbol"),
            "score": row.get("score"),
            "trend": row.get("trend"),
            "action": row.get("action"),
        }
        for row in sorted_rows[-5:][::-1]
    ]

    risk_alerts: list[dict[str, Any]] = []
    for row in report_rows:
        alerts = row.get("risk_alerts", [])
        if isinstance(alerts, list):
            for alert in alerts:
                risk_alerts.append({"symbol": row.get("symbol"), "alert": str(alert)})

    industry_summary = _build_industry_summary(
        report_rows=report_rows,
        industry_map=industry_map or {},
        history_by_symbol=history_by_symbol or {},
        trend_window_days=max(1, trend_window_days),
        risk_top_n=max(1, risk_top_n),
        weights=weights,
    )

    return {
        "total": len(report_rows),
        "avg_score": avg_score,
        "trend_counts": dict(trend_counts),
        "action_counts": dict(action_counts),
        "top": top,
        "bottom": bottom,
        "risk_alerts": risk_alerts,
        "industry": industry_summary,
    }


def _build_industry_summary(
    *,
    report_rows: list[dict[str, Any]],
    industry_map: dict[str, list[str]],
    history_by_symbol: dict[str, list[dict[str, Any]]],
    trend_window_days: int,
    risk_top_n: int,
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    if not industry_map:
        return []
    symbol_to_industry: dict[str, list[str]] = defaultdict(list)
    for industry, symbols in industry_map.items():
        for symbol in symbols:
            symbol_to_industry[str(symbol).upper()].append(str(industry))

    industry_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report_rows:
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        for industry in symbol_to_industry.get(symbol, []):
            industry_groups[industry].append(row)

    summary: list[dict[str, Any]] = []
    for industry, rows in industry_groups.items():
        scores = [row.get("score") for row in rows]
        numeric_scores = [float(s) for s in scores if isinstance(s, int | float)]
        avg_score = (
            sum(numeric_scores) / len(numeric_scores) if numeric_scores else None
        )
        trend_counts = Counter(str(row.get("trend", "unknown")) for row in rows)
        action_counts = Counter(str(row.get("action", "unknown")) for row in rows)
        top_row = max(
            rows, key=lambda item: _safe_score(item.get("score")), default=None
        )

        action_score = _compute_action_score(action_counts, weights)
        score_weight = weights["score_weight"]
        norm_avg_score = (avg_score / 100.0) if avg_score is not None else 0.0
        recommend_score = (
            action_score * (1.0 - score_weight) + norm_avg_score * score_weight
        )
        recommend_level = _recommend_level(recommend_score)

        trend_change_count = _compute_trend_change_count(
            rows=rows,
            history_by_symbol=history_by_symbol,
            trend_window_days=trend_window_days,
        )
        risk_top = _industry_risk_top(rows=rows, risk_top_n=risk_top_n)

        summary.append(
            {
                "industry": industry,
                "count": len(rows),
                "avg_score": avg_score,
                "trend_counts": dict(trend_counts),
                "action_counts": dict(action_counts),
                "top_symbol": top_row.get("symbol") if top_row else None,
                "top_score": top_row.get("score") if top_row else None,
                "trend_change_count": trend_change_count,
                "risk_top": risk_top,
                "recommend_score": round(recommend_score, 4),
                "recommend_level": recommend_level,
            }
        )

    summary.sort(
        key=lambda item: _safe_score(item.get("recommend_score")), reverse=True
    )
    return summary


def _compute_action_score(
    action_counts: Counter[str], weights: dict[str, float]
) -> float:
    total = sum(action_counts.values())
    if total <= 0:
        return 0.0
    score = 0.0
    for action, count in action_counts.items():
        key = str(action).lower()
        score += weights.get(key, 0.0) * count
    return score / total


def _compute_trend_change_count(
    *,
    rows: list[dict[str, Any]],
    history_by_symbol: dict[str, list[dict[str, Any]]],
    trend_window_days: int,
) -> int:
    changed = 0
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        history = history_by_symbol.get(symbol, [])[: max(2, trend_window_days)]
        if len(history) < 2:
            continue
        latest_action = str(history[0].get("action", "")).lower()
        prev_action = str(history[1].get("action", "")).lower()
        if latest_action and prev_action and latest_action != prev_action:
            changed += 1
    return changed


def _industry_risk_top(
    *, rows: list[dict[str, Any]], risk_top_n: int
) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        alerts = row.get("risk_alerts", [])
        if not isinstance(alerts, list):
            continue
        for alert in alerts:
            text = str(alert).strip()
            if text:
                counter[text] += 1
    return [
        {"alert": alert, "count": count}
        for alert, count in counter.most_common(risk_top_n)
    ]


def _recommend_level(score: float) -> str:
    if score >= 0.4:
        return "overweight"
    if score <= -0.2:
        return "underweight"
    return "neutral"


def _normalize_weights(value: dict[str, float] | None) -> dict[str, float]:
    if not value:
        return {
            "buy": 1.0,
            "hold": 0.0,
            "sell": -1.0,
            "score_weight": 0.5,
        }
    return {
        "buy": float(value.get("buy", 1.0)),
        "hold": float(value.get("hold", 0.0)),
        "sell": float(value.get("sell", -1.0)),
        "score_weight": float(value.get("score_weight", 0.5)),
    }


def _safe_score(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
