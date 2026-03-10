from __future__ import annotations

from datetime import timedelta

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    Action,
    AnalysisTask,
    Confidence,
    EtfAnalysisResult,
    EtfRealtimeQuote,
    TaskStatus,
    Trend,
)
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.repositories.repository import EtfAnalysisReportORM
from daily_etf_analysis.services.data_lifecycle_service import DataLifecycleService


def test_data_lifecycle_cleanup_dry_run_and_execute(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "lifecycle.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        retention_task_days=7,
        retention_report_days=7,
        retention_quote_days=7,
    )
    repo = EtfRepository(settings)

    now = utc_now_naive()
    old_time = now - timedelta(days=10)

    repo.create_task(
        AnalysisTask(
            task_id="old-task",
            status=TaskStatus.COMPLETED,
            symbols=["CN:159659"],
            force_refresh=False,
            created_at=old_time,
            updated_at=old_time,
        )
    )
    repo.create_task(
        AnalysisTask(
            task_id="new-task",
            status=TaskStatus.COMPLETED,
            symbols=["US:QQQ"],
            force_refresh=False,
            created_at=now,
            updated_at=now,
        )
    )

    repo.save_realtime_quote(
        EtfRealtimeQuote(symbol="CN:159659", price=1.0, quote_time=old_time)
    )
    repo.save_realtime_quote(
        EtfRealtimeQuote(symbol="US:QQQ", price=2.0, quote_time=now)
    )

    repo.save_analysis_report(
        task_id="old-task",
        symbol="CN:159659",
        trade_date=old_time.date(),
        factors={},
        result=EtfAnalysisResult(
            symbol="CN:159659",
            score=80,
            trend=Trend.BULLISH,
            action=Action.BUY,
            confidence=Confidence.HIGH,
            summary="old",
        ),
    )
    repo.save_analysis_report(
        task_id="new-task",
        symbol="US:QQQ",
        trade_date=now.date(),
        factors={},
        result=EtfAnalysisResult(
            symbol="US:QQQ",
            score=60,
            trend=Trend.NEUTRAL,
            action=Action.HOLD,
            confidence=Confidence.MEDIUM,
            summary="new",
        ),
    )

    with repo.session() as db:
        first_report = (
            db.query(EtfAnalysisReportORM)
            .filter(EtfAnalysisReportORM.task_id == "old-task")
            .first()
        )
        assert first_report is not None
        first_report.created_at = old_time

    service = DataLifecycleService(settings=settings, repository=repo)

    dry_result = service.cleanup(dry_run=True, actor="tester")
    assert dry_result["dry_run"] is True
    assert dry_result["impacted"]["tasks"] >= 1
    assert dry_result["impacted"]["reports"] >= 1
    assert dry_result["impacted"]["quotes"] >= 1
    assert dry_result["deleted"] == {"tasks": 0, "reports": 0, "quotes": 0}

    execute_result = service.cleanup(dry_run=False, actor="tester")
    assert execute_result["dry_run"] is False
    assert execute_result["deleted"]["tasks"] >= 1
    assert execute_result["deleted"]["reports"] >= 1
    assert execute_result["deleted"]["quotes"] >= 1
