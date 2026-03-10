from __future__ import annotations

from datetime import date
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.observability.metrics import inc_report_render


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
    market_review: dict[str, Any] | None = None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
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
            market_review=market_review,
            history_by_symbol=history_by_symbol,
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

    market_review_block = ""
    if market_review:
        market_review_block = _render_market_review_section(market_review)

    history_block = ""
    if history_by_symbol:
        history_block = _render_history_section(history_by_symbol)

    inc_report_render("fallback")
    return (
        "# Daily ETF Analysis Report\n\n"
        "## Summary\n"
        f"- Task ID: {task_id}\n"
        f"- Status: {status}\n"
        f"- Date: {report_date.isoformat()}\n"
        f"- Market: {market}\n"
        f"- Symbols analyzed: {len(report_rows)}\n\n"
        "## Top Symbols\n"
        f"{top_section}\n\n"
        "## Risk Alerts\n"
        f"{risk_section}\n\n"
        f"{market_review_block}"
        f"{history_block}"
        f"{notes_block}"
        f"Disclaimer: {disclaimer}\n"
    )


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


def _render_market_review_section(market_review: dict[str, Any]) -> str:
    avg_score = market_review.get("avg_score")
    trend_counts = market_review.get("trend_counts", {})
    action_counts = market_review.get("action_counts", {})
    top = market_review.get("top", [])
    bottom = market_review.get("bottom", [])

    trend_line = ", ".join(f"{k}={v}" for k, v in trend_counts.items()) or "-"
    action_line = ", ".join(f"{k}={v}" for k, v in action_counts.items()) or "-"

    top_lines = [
        f"- {row.get('symbol', '-')}: score={row.get('score', '-')}, action={row.get('action', '-')}"
        for row in top
    ]
    bottom_lines = [
        f"- {row.get('symbol', '-')}: score={row.get('score', '-')}, action={row.get('action', '-')}"
        for row in bottom
    ]

    top_section = "\n".join(top_lines) if top_lines else "- No data"
    bottom_section = "\n".join(bottom_lines) if bottom_lines else "- No data"

    industry_lines = _render_industry_lines(market_review.get("industry", []))
    industry_section = ""
    if industry_lines:
        industry_section = f"### Industry Summary\n{industry_lines}\n\n"

    return (
        "## Market Review\n"
        f"- Avg score: {avg_score if avg_score is not None else '-'}\n"
        f"- Trend distribution: {trend_line}\n"
        f"- Action distribution: {action_line}\n\n"
        "### Top ETFs\n"
        f"{top_section}\n\n"
        "### Bottom ETFs\n"
        f"{bottom_section}\n\n"
        f"{industry_section}"
    )


def _render_industry_lines(industry_rows: list[dict[str, Any]]) -> str:
    if not industry_rows:
        return "- No industry mapping"
    lines = []
    for row in industry_rows:
        industry = row.get("industry", "-")
        count = row.get("count", "-")
        avg_score = row.get("avg_score")
        top_symbol = row.get("top_symbol") or "-"
        action_counts = row.get("action_counts", {})
        recommend_level = row.get("recommend_level", "-")
        recommend_score = row.get("recommend_score", "-")
        trend_change_count = row.get("trend_change_count", 0)
        risk_top = row.get("risk_top", [])
        action_line = ", ".join(f"{k}={v}" for k, v in action_counts.items()) or "-"
        risk_text = "; ".join(
            f"{item.get('alert', '-')}({item.get('count', 0)})" for item in risk_top
        )
        if not risk_text:
            risk_text = "-"
        lines.append(
            f"- {industry}: count={count}, avg_score={avg_score}, top={top_symbol}, "
            f"actions={action_line}, recommend={recommend_level}({recommend_score}), "
            f"trend_changes={trend_change_count}, risk_top={risk_text}"
        )
    return "\n".join(lines)


def _render_history_section(history_by_symbol: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = ["## History Signals"]
    for symbol, items in history_by_symbol.items():
        if not items:
            continue
        entries = ", ".join(
            f"{item.get('trade_date')}:{item.get('action', '-')}/{item.get('trend', '-')}/{item.get('score', '-')}"
            for item in items
        )
        lines.append(f"- {symbol}: {entries}")
    if len(lines) == 1:
        lines.append("- No history data")
    return "\n".join(lines) + "\n\n"


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
    market_review: dict[str, Any] | None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None,
) -> str | None:
    settings = get_settings()
    env = Environment(
        loader=FileSystemLoader(settings.report_templates_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        template = env.get_template("report_markdown.j2")
    except TemplateNotFound:
        return None
    payload = {
        "task_id": task_id,
        "status": status,
        "report_date": report_date,
        "market": market,
        "report_rows": report_rows,
        "disclaimer": disclaimer,
        "notes": notes,
        "skip_reason": skip_reason,
        "market_review": market_review,
        "history_by_symbol": history_by_symbol,
    }
    return template.render(**payload)
