from __future__ import annotations

import time

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.task_manager import TaskManager


class _PipelineStub:
    def run(self, task_id: str, symbols: list[str], force_refresh: bool = False):  # type: ignore[no-untyped-def]
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
