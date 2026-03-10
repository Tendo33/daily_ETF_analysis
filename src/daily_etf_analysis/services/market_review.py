from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_market_review(
    report_rows: list[dict[str, Any]],
    *,
    industry_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
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
        report_rows=report_rows, industry_map=industry_map or {}
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
    *, report_rows: list[dict[str, Any]], industry_map: dict[str, list[str]]
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
        summary.append(
            {
                "industry": industry,
                "count": len(rows),
                "avg_score": avg_score,
                "trend_counts": dict(trend_counts),
                "action_counts": dict(action_counts),
                "top_symbol": top_row.get("symbol") if top_row else None,
                "top_score": top_row.get("score") if top_row else None,
            }
        )

    summary.sort(key=lambda item: _safe_score(item.get("avg_score")), reverse=True)
    return summary


def _safe_score(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
