from __future__ import annotations

import threading
import time
from types import SimpleNamespace

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
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        for _ in range(100):
            if cancel_event is not None and cancel_event.is_set():
                break
            if self._event.wait(timeout=0.1):
                break
        return []


class _SlowPipeline:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        deadline = time.time() + self.delay_seconds
        while time.time() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                break
            time.sleep(0.05)
        return []


class _IgnoreCancelBlockingPipeline:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self._release = threading.Event()

    def release(self) -> None:
        self._release.set()

    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        self.started.set()
        self._release.wait(timeout=5.0)
        self.finished.set()
        return []


class _FailingPipeline:
    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        raise RuntimeError("simulated failure")


class _SkippingPipeline:
    def run(  # type: ignore[no-untyped-def]
        self,
        task_id: str,
        symbols: list[str],
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event=None,
    ):
        return SimpleNamespace(
            analyzed_count=0,
            skipped_count=len(symbols),
            skipped_symbols=symbols,
            skip_reason="all markets closed",
        )


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


def test_task_queue_executes_pending_tasks(tmp_path) -> None:  # type: ignore[no-untyped-def]
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
    task3 = manager.submit(["HK:02800"])

    assert task1.status.value == "pending"
    assert task2.status.value == "pending"
    assert task3.status.value == "pending"

    pipeline.release()
    status1 = _wait_status(manager, task1.task_id, {"completed", "failed"})
    status2 = _wait_status(manager, task2.task_id, {"completed", "failed"})
    status3 = _wait_status(manager, task3.task_id, {"completed", "failed"})
    assert status1 == "completed"
    assert status2 == "completed"
    assert status3 == "completed"
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


def test_active_task_dedup_blocks_duplicate_symbol(tmp_path) -> None:  # type: ignore[no-untyped-def]
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


def test_failed_task_can_retry_immediately_within_dedup_window(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_retry_after_failure.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=30,
        task_dedup_window_seconds=60,
    )
    repo = EtfRepository(settings)
    manager = TaskManager(
        repository=repo,
        pipeline=_FailingPipeline(),  # type: ignore[arg-type]
        settings=settings,
    )
    first = manager.submit(["CN:159659"])
    status = _wait_status(manager, first.task_id, {"failed"})
    assert status == "failed"

    second = manager.submit(["CN:159659"])
    assert second.task_id != first.task_id
    manager.shutdown()


def test_force_retry_bypasses_active_task_dedup(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_force_retry.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=30,
        task_dedup_window_seconds=60,
    )
    repo = EtfRepository(settings)
    pipeline = _BlockingPipeline()
    manager = TaskManager(repository=repo, pipeline=pipeline, settings=settings)  # type: ignore[arg-type]

    _ = manager.submit(["CN:159659"])
    forced = manager.submit(["CN:159659"], force_retry=True)
    assert forced.task_id
    pipeline.release()
    manager.shutdown()


def test_run_window_lock_blocks_parallel_window(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_run_window_lock.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=30,
        task_dedup_window_seconds=60,
    )
    repo = EtfRepository(settings)
    pipeline = _BlockingPipeline()
    manager = TaskManager(repository=repo, pipeline=pipeline, settings=settings)  # type: ignore[arg-type]

    manager.submit_many(["CN:159659"], run_window="cn:2026-03-11")
    with pytest.raises(ValueError, match="Run window lock active"):
        manager.submit_many(["US:QQQ"], run_window="cn:2026-03-11")

    pipeline.release()
    manager.shutdown()


def test_all_skipped_task_marked_completed_with_skip_fields(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_skipped.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=30,
        task_dedup_window_seconds=0,
    )
    repo = EtfRepository(settings)
    manager = TaskManager(
        repository=repo,
        pipeline=_SkippingPipeline(),  # type: ignore[arg-type]
        settings=settings,
    )
    task = manager.submit(["CN:159659"])
    final_status = _wait_status(manager, task.task_id, {"completed", "failed"})
    assert final_status == "completed"
    final_task = manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.skip_reason == "all markets closed"
    assert final_task.skipped_symbols == ["CN:159659"]
    manager.shutdown()


def test_timeout_keeps_symbol_dedup_active_until_worker_stops(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "task_timeout_symbol_active.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        task_max_concurrency=1,
        task_queue_max_size=5,
        task_timeout_seconds=1,
        task_dedup_window_seconds=60,
    )
    repo = EtfRepository(settings)
    pipeline = _IgnoreCancelBlockingPipeline()
    manager = TaskManager(repository=repo, pipeline=pipeline, settings=settings)  # type: ignore[arg-type]

    first = manager.submit(["CN:159659"])
    first_status = _wait_status(manager, first.task_id, {"failed"})
    assert first_status == "failed"
    assert pipeline.started.is_set() is True
    assert pipeline.finished.is_set() is False

    with pytest.raises(ValueError, match="dedup"):
        manager.submit(["CN:159659"])

    pipeline.release()
    manager.shutdown()
