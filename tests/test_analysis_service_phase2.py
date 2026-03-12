from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisResult,
    EtfRealtimeQuote,
    Trend,
)
from daily_etf_analysis.services.analysis_service import AnalysisService


def _build_service(tmp_path: Path) -> AnalysisService:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'phase2.db'}",
        etf_list=["US:QQQ", "CN:159659"],
        index_proxy_map={"NDX": ["US:QQQ", "CN:159659"]},
    )
    return AnalysisService(settings=settings)


def test_get_index_comparison_sorts_and_ranks(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    report_date = date(2026, 3, 9)

    service.repository.save_analysis_report(
        task_id="t1",
        symbol="US:QQQ",
        trade_date=report_date,
        factors={"return_20": 0.12, "return_60": 0.24},
        result=EtfAnalysisResult(
            symbol="US:QQQ",
            score=90,
            trend=Trend.BULLISH,
            action=Action.BUY,
            confidence=Confidence.HIGH,
            summary="Strong trend",
            model_used="openai/gpt-4o-mini",
        ),
    )
    service.repository.save_analysis_report(
        task_id="t1",
        symbol="CN:159659",
        trade_date=report_date,
        factors={"return_20": 0.06, "return_60": 0.08},
        result=EtfAnalysisResult(
            symbol="CN:159659",
            score=74,
            trend=Trend.NEUTRAL,
            action=Action.HOLD,
            confidence=Confidence.MEDIUM,
            summary="Neutral trend",
            model_used="openai/gpt-4o-mini",
        ),
    )
    service.repository.save_realtime_quote(
        quote=EtfRealtimeQuote(
            symbol="US:QQQ",
            price=500.0,
            change_pct=1.5,
            quote_time=datetime.now(UTC),
            source="mock",
        )
    )
    service.repository.save_realtime_quote(
        quote=EtfRealtimeQuote(
            symbol="CN:159659",
            price=1.23,
            change_pct=0.2,
            quote_time=datetime.now(UTC),
            source="mock",
        )
    )

    result = service.get_index_comparison(index_symbol="NDX", target_date=report_date)
    assert result.index_symbol == "NDX"
    assert result.report_date == report_date
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "US:QQQ"
    assert result.rows[0].rank == 1
    assert result.rows[1].symbol == "CN:159659"
    assert result.rows[1].rank == 2


def test_get_index_comparison_raises_for_missing_mapping(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    with pytest.raises(ValueError):
        service.get_index_comparison(index_symbol="SPX", target_date=None)


def test_get_task_report_date_returns_latest_trade_date(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service.repository.save_analysis_report(
        task_id="task-abc",
        symbol="US:QQQ",
        trade_date=date(2026, 3, 7),
        factors={},
        result=EtfAnalysisResult.neutral_fallback("US:QQQ", "x"),
    )
    service.repository.save_analysis_report(
        task_id="task-abc",
        symbol="CN:159659",
        trade_date=date(2026, 3, 9),
        factors={},
        result=EtfAnalysisResult.neutral_fallback("CN:159659", "y"),
    )

    assert service.get_task_report_date("task-abc") == date(2026, 3, 9)


def test_get_task_report_date_returns_none_when_missing(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    assert service.get_task_report_date("not-found") is None


def test_create_analysis_run_failure_records_failed_run(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    service = _build_service(tmp_path)

    monkeypatch.setattr(
        "daily_etf_analysis.services.analysis_service.uuid.uuid4",
        lambda: SimpleNamespace(hex="run-failed-1"),
    )

    def _boom(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(service.repository, "create_analysis_run_with_tasks", _boom)

    with pytest.raises(RuntimeError):
        service.create_analysis_run(symbols=["US:QQQ"], source="test")

    run = service.repository.get_analysis_run("run-failed-1")
    assert run is not None
    assert run.status.value == "failed"
    logs = service.repository.list_analysis_run_audit_logs("run-failed-1", limit=10)
    assert any(item.get("event_type") == "run_failed" for item in logs)
