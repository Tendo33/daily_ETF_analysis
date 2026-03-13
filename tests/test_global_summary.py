from __future__ import annotations

from datetime import date

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.services.global_summary import build_global_summary_text


def test_global_summary_fallback_without_llm() -> None:
    rows = [
        {
            "symbol": "CN:159392",
            "score": 55,
            "action": "hold",
            "trend": "neutral",
            "risk_alerts": ["波动放大"],
            "context_snapshot": {},
        }
    ]
    text = build_global_summary_text(
        report_rows=rows, report_date=date(2026, 3, 12), settings=Settings()
    )
    assert "一句话结论" in text


def test_global_summary_when_no_rows() -> None:
    text = build_global_summary_text(
        report_rows=[], report_date=date(2026, 3, 12), settings=Settings()
    )
    assert "无可用ETF" in text
