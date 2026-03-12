from __future__ import annotations

import time

from sqlalchemy import select

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import AnalysisTask, TaskStatus
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.repositories.models import AnalysisTaskORM
from daily_etf_analysis.services.task_manager import TaskManager


class _PipelineStub:
    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        return []


def test_task_status_flow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_manager.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    repo = EtfRepository(settings)
    manager = TaskManager(repository=repo, pipeline=_PipelineStub())  # type: ignore[arg-type]

    task = manager.submit(["CN:159659"], force_refresh=False)
    assert task.status.value == "pending"

    deadline = time.time() + 3
    current = None
    while time.time() < deadline:
        current = manager.get_task(task.task_id)
        if current and current.status.value in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert current is not None
    assert current.status.value == "completed"
    manager.shutdown()


def test_legacy_task_status_values_are_mapped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "legacy_task_status.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    repo = EtfRepository(settings)
    task = AnalysisTask(
        task_id="legacy-status-task",
        status=TaskStatus.PENDING,
        symbols=["CN:159659"],
        force_refresh=False,
    )
    repo.create_task(task)

    mappings = {
        "queued": "pending",
        "running": "processing",
        "skipped": "completed",
    }
    for legacy, expected in mappings.items():
        with repo.session() as db:
            row = db.execute(
                select(AnalysisTaskORM).where(
                    AnalysisTaskORM.task_id == "legacy-status-task"
                )
            ).scalar_one()
            row.status = legacy
        mapped = repo.get_task("legacy-status-task")
        assert mapped is not None
        assert mapped.status.value == expected
