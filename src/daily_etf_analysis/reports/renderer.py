from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.observability.metrics import inc_report_render


@dataclass(slots=True)
class ResultView:
    symbol: str
    code: str
    name: str
    sentiment_score: int
    trend_prediction: str
    operation_advice: str
    decision_type: str
    dashboard: dict[str, Any]
    analysis_summary: str
    buy_reason: str
    risk_warning: str
    market_snapshot: dict[str, Any]
    theme_tags: list[str]
    theme_intel: dict[str, Any]
    etf_features: dict[str, Any]


def render_daily_report_markdown(
    *,
    task_id: str,
    status: str,
    report_date: date,
    market: str,
    report_rows: list[dict[str, Any]],
    disclaimer: str,
    notes: str | None = None,
    skip_reason: str | None = None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
    global_summary_text: str | None = None,
) -> str:
    settings = get_settings()
    normalized_rows, integrity_notes = _normalize_report_rows(
        report_rows, settings.report_integrity_enabled
    )
    report_rows = normalized_rows

    if settings.report_renderer_enabled:
        template_markdown = _render_with_template(
            task_id=task_id,
            status=status,
            report_date=report_date,
            market=market,
            report_rows=report_rows,
            disclaimer=disclaimer,
            notes=_merge_notes(notes, integrity_notes),
            skip_reason=skip_reason,
            history_by_symbol=history_by_symbol,
            global_summary_text=global_summary_text,
        )
        if template_markdown:
            inc_report_render("template")
            return template_markdown

    top_lines = []
    for row in sorted(
        report_rows, key=lambda item: float(item.get("score", 0)), reverse=True
    )[:5]:
        summary = str(row.get("summary", "")).strip()
        summary_text = f" | {summary}" if summary else ""
        key_points = row.get("key_points", [])
        if isinstance(key_points, list):
            points = "; ".join(str(item) for item in key_points if str(item).strip())
        else:
            points = ""
        points_text = f" | points: {points}" if points else ""
        top_lines.append(
            f"- {row.get('symbol', '-')}: action={row.get('action', '-')}, "
            f"trend={row.get('trend', '-')}, score={row.get('score', '-')}"
            f"{summary_text}{points_text}"
        )

    risk_lines: list[str] = []
    for row in report_rows:
        symbol = str(row.get("symbol", "-"))
        alerts = row.get("risk_alerts", [])
        if isinstance(alerts, list) and alerts:
            for alert in alerts:
                risk_lines.append(f"- {symbol}: {alert}")

    top_section = "\n".join(top_lines) if top_lines else "- No symbols"
    risk_section = "\n".join(risk_lines) if risk_lines else "- No risk alerts"

    notes_block = ""
    if skip_reason:
        notes_block = f"## Notes\n- {skip_reason}\n\n"
    else:
        merged_notes = _merge_notes(notes, integrity_notes)
        if merged_notes:
            notes_block = f"## Notes\n{merged_notes}\n\n"

    history_block = ""
    if history_by_symbol:
        history_block = _render_history_section(history_by_symbol)

    global_summary_block = ""
    if global_summary_text:
        global_summary_block = f"## Global Summary\n{global_summary_text}\n\n"

    inc_report_render("fallback")
    return (
        "# Daily ETF Analysis Report\n\n"
        "## Summary\n"
        f"- Task ID: {task_id}\n"
        f"- Status: {status}\n"
        f"- Date: {report_date.isoformat()}\n"
        f"- Market: {market}\n"
        f"- Symbols analyzed: {len(report_rows)}\n\n"
        f"{global_summary_block}"
        "## Top Symbols\n"
        f"{top_section}\n\n"
        "## Risk Alerts\n"
        f"{risk_section}\n\n"
        f"{history_block}"
        f"{notes_block}"
        f"Disclaimer: {disclaimer}\n"
    )


def _render_with_template(
    *,
    task_id: str,
    status: str,
    report_date: date,
    market: str,
    report_rows: list[dict[str, Any]],
    disclaimer: str,
    notes: str | None,
    skip_reason: str | None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None,
    global_summary_text: str | None,
) -> str | None:
    settings = get_settings()
    templates_dir = _resolve_templates_dir(settings.report_templates_dir)
    report_type = (settings.report_type or "simple").lower()
    if report_type == "brief":
        template_name = "report_brief.j2"
    else:
        template_name = "report_markdown.j2"

    context = _build_template_context(
        report_rows=report_rows,
        report_date=report_date,
        summary_only=settings.report_summary_only,
        history_by_symbol=history_by_symbol,
        global_summary_text=global_summary_text,
    )
    context.update(
        {
            "task_id": task_id,
            "status": status,
            "market": market,
            "notes": notes,
            "skip_reason": skip_reason,
            "disclaimer": disclaimer,
        }
    )

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(default=False),
    )
    try:
        template = env.get_template(template_name)
    except TemplateNotFound:
        return None
    try:
        return template.render(**context)
    except Exception:
        return None


def _resolve_templates_dir(template_dir: str) -> Path:
    base = Path(__file__).resolve().parents[3]
    path = Path(template_dir)
    if not path.is_absolute():
        return base / path
    return path


def _build_template_context(
    *,
    report_rows: list[dict[str, Any]],
    report_date: date,
    summary_only: bool,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None,
    global_summary_text: str | None,
) -> dict[str, Any]:
    results: list[ResultView] = []
    for row in report_rows:
        symbol = str(row.get("symbol", ""))
        code = symbol.split(":", 1)[-1] if symbol else ""
        context_snapshot = row.get("context_snapshot", {})
        if not isinstance(context_snapshot, dict):
            context_snapshot = {}
        payload = context_snapshot.get("llm_payload", {})
        if not isinstance(payload, dict):
            payload = {}
        dashboard = payload.get("dashboard") or {}
        analysis_summary = str(
            payload.get("analysis_summary") or row.get("summary") or ""
        ).strip()
        operation_advice = str(
            payload.get("operation_advice")
            or _operation_from_action(str(row.get("action", "hold")))
        ).strip()
        sentiment_score = _to_int(payload.get("sentiment_score"), row.get("score"))
        trend_prediction = str(
            payload.get("trend_prediction") or row.get("trend") or ""
        ).strip()
        decision_type = str(
            payload.get("decision_type") or row.get("action") or "hold"
        ).lower()
        name = str(payload.get("stock_name") or symbol or code)
        market_snapshot = context_snapshot.get("market_snapshot", {})
        if not isinstance(market_snapshot, dict):
            market_snapshot = {}
        factors = row.get("factors", {})
        if not isinstance(factors, dict):
            factors = {}
        theme_tags = _normalize_list(factors.get("theme_tags"))
        theme_intel = factors.get("theme_intel")
        if not isinstance(theme_intel, dict):
            theme_intel = {}
        etf_features = factors.get("etf_features")
        if not isinstance(etf_features, dict):
            etf_features = {}

        dashboard = _ensure_dashboard(dashboard, factors, market_snapshot)

        results.append(
            ResultView(
                symbol=symbol,
                code=code,
                name=name,
                sentiment_score=sentiment_score,
                trend_prediction=trend_prediction,
                operation_advice=operation_advice,
                decision_type=decision_type,
                dashboard=dashboard,
                analysis_summary=analysis_summary,
                buy_reason=str(payload.get("buy_reason") or ""),
                risk_warning=str(payload.get("risk_warning") or ""),
                market_snapshot=market_snapshot,
                theme_tags=theme_tags,
                theme_intel=theme_intel,
                etf_features=etf_features,
            )
        )

    sorted_results = sorted(results, key=lambda item: item.sentiment_score, reverse=True)
    enriched: list[dict[str, Any]] = []
    for result in sorted_results:
        signal_text, signal_emoji, _ = _get_signal_level(result)
        enriched.append(
            {
                "result": result,
                "signal_text": signal_text,
                "signal_emoji": signal_emoji,
                "stock_name": _escape_md(result.name),
            }
        )

    buy_count = sum(1 for r in results if r.decision_type == "buy")
    sell_count = sum(1 for r in results if r.decision_type == "sell")
    hold_count = sum(1 for r in results if r.decision_type not in {"buy", "sell"})

    report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_by_code = _remap_history(history_by_symbol or {})

    return {
        "report_date": report_date.isoformat(),
        "report_timestamp": report_timestamp,
        "results": sorted_results,
        "enriched": enriched,
        "summary_only": summary_only,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "hold_count": hold_count,
        "escape_md": _escape_md,
        "clean_sniper": _clean_sniper_value,
        "history_by_code": history_by_code,
        "history_by_symbol": history_by_symbol or {},
        "global_summary_text": global_summary_text,
    }


def _ensure_dashboard(
    dashboard: dict[str, Any] | object,
    factors: dict[str, Any],
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(dashboard, dict):
        dashboard_payload: dict[str, Any] = {}
    else:
        dashboard_payload = dict(dashboard)
    data_perspective = dashboard_payload.get("data_perspective")
    if not isinstance(data_perspective, dict) or not data_perspective:
        fallback = _build_data_perspective(factors, market_snapshot)
        if fallback:
            dashboard_payload["data_perspective"] = fallback
    else:
        etf_structure = _build_etf_structure(factors)
        if etf_structure:
            data_perspective.setdefault("etf_structure", etf_structure)
            dashboard_payload["data_perspective"] = data_perspective

    theme_intel = factors.get("theme_intel")
    if isinstance(theme_intel, dict) and theme_intel:
        intelligence = dashboard_payload.get("intelligence")
        dashboard_payload["intelligence"] = _merge_intelligence(
            intelligence, theme_intel
        )
    return dashboard_payload


def _build_data_perspective(
    factors: dict[str, Any], market_snapshot: dict[str, Any]
) -> dict[str, Any]:
    if not factors and not market_snapshot:
        return {}
    ma5 = _to_float(factors.get("ma5"))
    ma10 = _to_float(factors.get("ma10"))
    ma20 = _to_float(factors.get("ma20"))
    trend_alignment = str(factors.get("trend_alignment") or "").strip().lower()
    bullish = bool(
        trend_alignment == "bullish"
        or (
            ma5 is not None
            and ma10 is not None
            and ma20 is not None
            and ma5 > ma10 > ma20
        )
    )
    ma_alignment = _trend_alignment_label(trend_alignment, bullish)
    trend_score = _to_int(factors.get("trend_score"), 50)

    latest_price = (
        _to_float(factors.get("latest_price"))
        or _to_float(market_snapshot.get("price"))
        or _to_float(market_snapshot.get("close"))
    )
    bias_ma5 = _to_float(factors.get("bias_ma5"))
    bias_status = str(factors.get("bias_status") or "N/A")
    support_level = _to_float(factors.get("support_level"))
    resistance_level = _to_float(factors.get("resistance_level"))

    volume_ratio = _to_float(factors.get("volume_ratio"))
    if volume_ratio is None:
        volume_ratio = _to_float(market_snapshot.get("volume_ratio"))
    volume_status = str(factors.get("volume_status") or "N/A")
    turnover_rate = _to_float(market_snapshot.get("turnover_rate"))
    if turnover_rate is None:
        turnover_rate = _to_float(factors.get("turnover"))
    data_quality = str(factors.get("data_quality") or "").strip().lower()
    volume_meaning = _volume_meaning(volume_status, data_quality)

    chip_structure = factors.get("chip_structure")
    if not isinstance(chip_structure, dict):
        chip_structure = {}
    chip_payload = {
        "profit_ratio": chip_structure.get("profit_ratio", "N/A"),
        "avg_cost": chip_structure.get("avg_cost", "N/A"),
        "concentration": chip_structure.get("concentration", "N/A"),
        "chip_health": chip_structure.get("chip_health", "N/A"),
    }

    return {
        "trend_status": {
            "ma_alignment": ma_alignment,
            "is_bullish": bullish,
            "trend_score": trend_score,
        },
        "price_position": {
            "current_price": latest_price,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "bias_ma5": bias_ma5,
            "bias_status": bias_status,
            "support_level": support_level,
            "resistance_level": resistance_level,
        },
        "volume_analysis": {
            "volume_ratio": volume_ratio,
            "volume_status": volume_status,
            "turnover_rate": turnover_rate,
            "volume_meaning": volume_meaning,
        },
        "chip_structure": chip_payload,
        "etf_structure": _build_etf_structure(factors),
    }


def _build_etf_structure(factors: dict[str, Any]) -> dict[str, Any]:
    etf_features = factors.get("etf_features")
    if not isinstance(etf_features, dict):
        return {}
    payload = {
        "premium_discount_pct": etf_features.get("premium_discount_pct"),
        "tracking_error": etf_features.get("tracking_error"),
        "share_change_pct": etf_features.get("share_change_pct"),
        "aum_change_pct": etf_features.get("aum_change_pct"),
        "liquidity_score": etf_features.get("liquidity_score"),
        "spread_proxy": etf_features.get("spread_proxy"),
        "intraday_gap_pct": etf_features.get("intraday_gap_pct"),
        "data_quality": etf_features.get("data_quality"),
    }
    if not any(value is not None and value != "" for value in payload.values()):
        return {}
    return payload


def _merge_intelligence(
    existing: dict[str, Any] | object, theme_intel: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if not merged.get("latest_news"):
        merged["latest_news"] = theme_intel.get("latest_news", "")
    if not merged.get("positive_catalysts"):
        merged["positive_catalysts"] = theme_intel.get("positive_catalysts", [])
    if not merged.get("risk_alerts"):
        merged["risk_alerts"] = theme_intel.get("risk_alerts", [])
    if not merged.get("sentiment_summary"):
        merged["sentiment_summary"] = theme_intel.get("sentiment_summary", "")
    return merged


def _remap_history(
    history_by_symbol: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    mapped: dict[str, list[dict[str, Any]]] = {}
    for symbol, items in history_by_symbol.items():
        code = symbol.split(":", 1)[-1] if symbol else symbol
        remapped: list[dict[str, Any]] = []
        for item in items:
            remapped.append(
                {
                    "created_at": item.get("trade_date"),
                    "sentiment_score": item.get("score"),
                    "operation_advice": _operation_from_action(
                        str(item.get("action", "hold"))
                    ),
                    "trend_prediction": item.get("trend"),
                }
            )
        mapped[code] = remapped
    return mapped


def _get_signal_level(result: ResultView) -> tuple[str, str, str]:
    advice = result.operation_advice
    score = result.sentiment_score
    advice_map = {
        "强烈买入": ("强烈买入", "💚", "强买"),
        "买入": ("买入", "🟢", "买入"),
        "加仓": ("买入", "🟢", "买入"),
        "持有": ("持有", "🟡", "持有"),
        "观望": ("观望", "⚪", "观望"),
        "减仓": ("减仓", "🟠", "减仓"),
        "卖出": ("卖出", "🔴", "卖出"),
        "强烈卖出": ("卖出", "🔴", "卖出"),
    }
    if advice in advice_map:
        return advice_map[advice]
    if score >= 80:
        return ("强烈买入", "💚", "强买")
    if score >= 65:
        return ("买入", "🟢", "买入")
    if score >= 55:
        return ("持有", "🟡", "持有")
    if score >= 45:
        return ("观望", "⚪", "观望")
    if score >= 35:
        return ("减仓", "🟠", "减仓")
    return ("卖出", "🔴", "卖出")


def _escape_md(text: str) -> str:
    if not text:
        return ""
    return text.replace("*", "\\*").replace("_", "\\_")


def _normalize_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _clean_sniper_value(val: Any) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, int | float):
        return str(val)
    s = str(val).strip() if val else ""
    if not s or s == "N/A":
        return s or "N/A"
    prefixes = [
        "理想买入点：",
        "次优买入点：",
        "止损位：",
        "目标位：",
        "理想买入点:",
        "次优买入点:",
        "止损位:",
        "目标位:",
    ]
    for prefix in prefixes:
        if s.startswith(prefix):
            return s[len(prefix) :]
    return s


def _operation_from_action(action: str) -> str:
    mapping = {"buy": "买入", "hold": "观望", "sell": "卖出"}
    return mapping.get(action.lower(), "观望")


def _to_int(value: object, fallback: object) -> int:
    for item in (value, fallback):
        if isinstance(item, int):
            return item
        if isinstance(item, float):
            return int(item)
        if isinstance(item, str) and item.isdigit():
            return int(item)
    return 50


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _trend_alignment_label(alignment: str, bullish: bool) -> str:
    if alignment == "bullish":
        return "多头排列"
    if alignment:
        return "非多头排列"
    return "多头排列" if bullish else "未知"


def _volume_meaning(volume_status: str, data_quality: str) -> str:
    base = ""
    if volume_status == "放量":
        base = "量能放大，关注趋势延续"
    elif volume_status == "缩量":
        base = "量能收缩，关注动能减弱"
    elif volume_status == "平量":
        base = "量能平稳"
    else:
        base = ""
    if data_quality and data_quality not in {"ok", "normal"}:
        note = f"数据质量:{data_quality}"
        if base:
            return f"{base}；{note}"
        return note
    return base


def _merge_notes(notes: str | None, integrity_notes: list[str]) -> str | None:
    merged: list[str] = []
    if notes:
        merged.append(notes.strip())
    merged.extend(integrity_notes)
    if not merged:
        return None
    return "\n".join(f"- {item}" for item in merged if item.strip())


def _normalize_report_rows(
    report_rows: list[dict[str, Any]], integrity_enabled: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    if not integrity_enabled:
        return report_rows, []
    notes: list[str] = []
    normalized: list[dict[str, Any]] = []
    for row in report_rows:
        if not isinstance(row, dict):
            continue
        payload = dict(row)
        missing: list[str] = []
        if payload.get("score") is None:
            payload["score"] = 50
            missing.append("score")
        if not payload.get("trend"):
            payload["trend"] = "neutral"
            missing.append("trend")
        if not payload.get("action"):
            payload["action"] = "hold"
            missing.append("action")
        if not payload.get("confidence"):
            payload["confidence"] = "low"
            missing.append("confidence")
        if payload.get("summary") is None:
            payload["summary"] = ""
            missing.append("summary")
        if not isinstance(payload.get("key_points"), list):
            payload["key_points"] = []
            missing.append("key_points")
        if not isinstance(payload.get("risk_alerts"), list):
            payload["risk_alerts"] = []
            missing.append("risk_alerts")
        normalized.append(payload)
        if missing:
            symbol = payload.get("symbol", "-")
            notes.append(f"{symbol}: filled missing {', '.join(missing)}")
    return normalized, notes




def _render_history_section(
    history_by_symbol: dict[str, list[dict[str, Any]]]
) -> str:
    lines = ["## History Signals"]
    for symbol, items in history_by_symbol.items():
        point = ", ".join(
            f"{item.get('trade_date')}:{item.get('action')}/{item.get('trend')}/{item.get('score')}"
            for item in items
        )
        lines.append(f"- {symbol}: {point}")
    return "\n".join(lines) + "\n\n"
