from __future__ import annotations

import threading
import time

import pytest

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.task_manager import TaskManager


class _BlockingPipeline:
    def __init__(self) -> None:
        self._event = threading.Event()

    def release(self) -> None:
        self._event.set()

    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        force_refresh: bool = False,
        skip_market_guard: bool = False,
    ):
        self._event.wait(timeout=10)
        return []


class _SlowPipeline:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        force_refresh: bool = False,
        skip_market_guard: bool = False,
    ):
        time.sleep(self.delay_seconds)
        return []


def _wait_status(
    manager: TaskManager, task_id: str, expected: set[str], timeout: float = 4.0
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = manager.get_task(task_id)
        if task is not None and task.status.value in expected:
            return task.status.value
        time.sleep(0.05)
    task = manager.get_task(task_id)
    return task.status.value if task is not None else "missing"


def test_task_queue_and_backpressure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_reliability.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=1,
        task_timeout_seconds=30,
        task_dedup_window_seconds=0,
    )
    repo = EtfRepository(settings)
    pipeline = _BlockingPipeline()
    manager = TaskManager(repository=repo, pipeline=pipeline, settings=settings)  # type: ignore[arg-type]

    task1 = manager.submit(["CN:159659"])
    task2 = manager.submit(["US:QQQ"])

    assert task1.status.value == "queued"
    assert task2.status.value == "queued"

    with pytest.raises(RuntimeError, match="queue is full"):
        manager.submit(["HK:02800"])

    pipeline.release()
    status1 = _wait_status(manager, task1.task_id, {"completed", "failed"})
    status2 = _wait_status(manager, task2.task_id, {"completed", "failed"})
    assert status1 == "completed"
    assert status2 == "completed"
    manager.shutdown()


def test_task_timeout_marks_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_timeout.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=1,
        task_dedup_window_seconds=0,
    )
    repo = EtfRepository(settings)
    manager = TaskManager(
        repository=repo,
        pipeline=_SlowPipeline(delay_seconds=2.5),  # type: ignore[arg-type]
        settings=settings,
    )

    start = time.perf_counter()
    task = manager.submit(["CN:159659"])
    final_status = _wait_status(manager, task.task_id, {"failed"}, timeout=4)
    elapsed = time.perf_counter() - start
    assert final_status == "failed"
    assert elapsed < 2.5

    failed_task = manager.get_task(task.task_id)
    assert failed_task is not None
    assert "timeout" in str(failed_task.error).lower()
    manager.shutdown()


def test_dedup_window_blocks_duplicate_symbol(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_dedup.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=30,
        task_dedup_window_seconds=30,
    )
    repo = EtfRepository(settings)
    pipeline = _BlockingPipeline()
    manager = TaskManager(repository=repo, pipeline=pipeline, settings=settings)  # type: ignore[arg-type]

    _ = manager.submit(["CN:159659"])
    with pytest.raises(ValueError, match="dedup"):
        manager.submit(["CN:159659"])

    pipeline.release()
    manager.shutdown()
