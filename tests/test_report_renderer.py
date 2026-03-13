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


def test_renderer_pretty_layout(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_RENDERER_ENABLED", "true")
    monkeypatch.setenv("REPORT_TEMPLATES_DIR", "templates")
    reload_settings()

    markdown = render_daily_report_markdown(
        task_id="t1",
        status="completed",
        report_date=date(2026, 3, 10),
        market="cn",
        report_rows=[
            {
                "symbol": "CN:159659",
                "score": 25,
                "trend": "bearish",
                "action": "hold",
                "confidence": "low",
                "summary": "test summary",
                "risk_alerts": ["risk 1"],
                "factors": {
                    "ma5": 1.0,
                    "ma10": 1.1,
                    "ma20": 1.2,
                    "bias_ma5": -0.5,
                    "bias_status": "安全",
                    "support_level": 0.9,
                    "resistance_level": 1.3,
                    "volume_ratio": 1.0,
                    "volume_status": "平量",
                    "trend_alignment": "non_bullish",
                    "trend_score": 25,
                    "theme_intel": {
                        "sentiment_summary": "偏谨慎",
                        "risk_alerts": ["风险点"],
                        "positive_catalysts": ["利好点"],
                        "latest_news": "最新消息",
                    },
                    "etf_features": {"liquidity_score": 65, "spread_proxy": 1.2},
                },
                "context_snapshot": {
                    "market_snapshot": {
                        "close": 1.0,
                        "prev_close": 1.1,
                        "open": 1.0,
                        "high": 1.2,
                        "low": 0.9,
                        "pct_chg": -0.5,
                        "change_amount": -0.1,
                        "amplitude": 2.0,
                        "volume": 1000,
                        "amount": 2000,
                        "price": 1.0,
                        "volume_ratio": 1.0,
                        "turnover_rate": 0.1,
                        "source": "mock",
                    }
                },
            }
        ],
        disclaimer="d",
    )

    assert "🎯 2026-03-10 决策仪表盘" in markdown
    assert "📰 重要信息速览" in markdown
    assert "📌 核心结论" in markdown
    assert "📈 当日行情" in markdown
    assert "📊 数据透视" in markdown
    assert "🎯 作战计划" in markdown
    assert "✅ 检查清单" in markdown
    assert "────────" in markdown
