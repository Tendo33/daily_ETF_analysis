from __future__ import annotations

from datetime import date

from daily_etf_analysis.reports.renderer import render_daily_report_markdown


def test_report_renderer_includes_required_sections() -> None:
    markdown = render_daily_report_markdown(
        task_id="task-1",
        status="completed",
        report_date=date(2026, 3, 9),
        market="all",
        report_rows=[
            {
                "symbol": "US:QQQ",
                "score": 88,
                "action": "buy",
                "risk_alerts": ["volatility rising"],
            },
            {
                "symbol": "CN:159659",
                "score": 75,
                "action": "hold",
                "risk_alerts": [],
            },
        ],
        disclaimer="For research only; not investment advice.",
    )

    assert "## Summary" in markdown
    assert "## Top Symbols" in markdown
    assert "## Risk Alerts" in markdown
    assert "US:QQQ" in markdown
    assert "For research only; not investment advice." in markdown
