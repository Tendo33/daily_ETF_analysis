from __future__ import annotations

from datetime import date

from daily_etf_analysis.config.settings import reload_settings
from daily_etf_analysis.reports.renderer import render_daily_report_markdown


def test_renderer_integrity_notes(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_INTEGRITY_ENABLED", "true")
    monkeypatch.setenv("REPORT_RENDERER_ENABLED", "false")
    reload_settings()

    markdown = render_daily_report_markdown(
        task_id="t1",
        status="completed",
        report_date=date(2026, 3, 10),
        market="cn",
        report_rows=[{"symbol": "CN:159659"}],
        disclaimer="d",
    )

    assert "filled missing" in markdown


def test_renderer_template(monkeypatch, tmp_path) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "report_markdown.j2").write_text(
        "TEMPLATE {{ task_id }}", encoding="utf-8"
    )

    monkeypatch.setenv("REPORT_RENDERER_ENABLED", "true")
    monkeypatch.setenv("REPORT_TEMPLATES_DIR", str(template_dir))
    reload_settings()

    markdown = render_daily_report_markdown(
        task_id="template-test",
        status="completed",
        report_date=date(2026, 3, 10),
        market="cn",
        report_rows=[],
        disclaimer="d",
    )

    assert "TEMPLATE template-test" in markdown


def test_renderer_history_section(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_RENDERER_ENABLED", "false")
    reload_settings()

    markdown = render_daily_report_markdown(
        task_id="t1",
        status="completed",
        report_date=date(2026, 3, 10),
        market="cn",
        report_rows=[],
        disclaimer="d",
        history_by_symbol={
            "CN:159659": [
                {
                    "trade_date": "2026-03-10",
                    "action": "buy",
                    "trend": "bullish",
                    "score": 80,
                }
            ]
        },
    )

    assert "History Signals" in markdown
    assert "CN:159659" in markdown


def test_renderer_industry_section(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_RENDERER_ENABLED", "false")
    reload_settings()

    markdown = render_daily_report_markdown(
        task_id="t1",
        status="completed",
        report_date=date(2026, 3, 10),
        market="cn",
        report_rows=[],
        disclaimer="d",
        market_review={
            "avg_score": 50,
            "trend_counts": {},
            "action_counts": {},
            "top": [],
            "bottom": [],
            "industry": [
                {
                    "industry": "Tech",
                    "count": 2,
                    "avg_score": 60,
                    "top_symbol": "CN:159659",
                    "action_counts": {"buy": 1},
                }
            ],
        },
    )

    assert "Industry Summary" in markdown
    assert "Tech" in markdown
