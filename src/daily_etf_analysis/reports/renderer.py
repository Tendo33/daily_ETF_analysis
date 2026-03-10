from __future__ import annotations

from datetime import date
from typing import Any


def render_daily_report_markdown(
    *,
    task_id: str,
    status: str,
    report_date: date,
    market: str,
    report_rows: list[dict[str, Any]],
    disclaimer: str,
) -> str:
    top_lines = []
    for row in sorted(
        report_rows, key=lambda item: float(item.get("score", 0)), reverse=True
    )[:5]:
        top_lines.append(
            f"- {row.get('symbol', '-')}: action={row.get('action', '-')}, score={row.get('score', '-')}"
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
        f"Disclaimer: {disclaimer}\n"
    )
