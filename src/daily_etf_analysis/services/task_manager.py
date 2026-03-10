from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import AnalysisTask, TaskStatus, normalize_symbol
from daily_etf_analysis.observability import inc_analysis_task
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline
from daily_etf_analysis.repositories import EtfRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _QueuedTask:
    task_id: str
    symbols: list[str]
    force_refresh: bool
    skip_market_guard: bool
    request_id: str | None


class TaskManager:
    def __init__(
        self,
        repository: EtfRepository,
        pipeline: DailyPipeline,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.settings = settings or get_settings()

        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.task_max_concurrency,
            thread_name_prefix="etf-analysis",
        )
        self._pipeline_executor = ThreadPoolExecutor(
            max_workers=self.settings.task_max_concurrency,
            thread_name_prefix="pipeline",
        )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pending_queue: deque[_QueuedTask] = deque()
        self._running_task_ids: set[str] = set()
        self._recent_symbol_submissions: dict[str, float] = {}

        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="task-dispatcher",
            daemon=True,
        )
        self._dispatcher.start()

    def submit(
        self,
        symbols: list[str],
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        request_id: str | None = None,
    ) -> AnalysisTask:
        normalized_symbols = [normalize_symbol(s) for s in symbols]
        now = time.monotonic()

        with self._lock:
            self._prune_recent_submissions(now)

            if self.settings.task_dedup_window_seconds > 0:
                dedup_hits = [
                    symbol
                    for symbol in normalized_symbols
                    if symbol in self._recent_symbol_submissions
                ]
                if dedup_hits:
                    joined = ", ".join(sorted(set(dedup_hits)))
                    raise ValueError(
                        f"Task dedup hit for symbols within window: {joined}"
                    )

            in_memory_capacity = (
                self.settings.task_max_concurrency + self.settings.task_queue_max_size
            )
            in_memory_load = len(self._running_task_ids) + len(self._pending_queue)
            if in_memory_load >= in_memory_capacity:
                raise RuntimeError("Task queue is full")

            task = AnalysisTask(
                task_id=uuid.uuid4().hex,
                status=TaskStatus.QUEUED,
                symbols=normalized_symbols,
                force_refresh=force_refresh,
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
            self.repository.create_task(task)
            inc_analysis_task(TaskStatus.QUEUED.value)

            self._pending_queue.append(
                _QueuedTask(
                    task_id=task.task_id,
                    symbols=normalized_symbols,
                    force_refresh=force_refresh,
                    skip_market_guard=skip_market_guard,
                    request_id=request_id,
                )
            )
            for symbol in normalized_symbols:
                self._recent_symbol_submissions[symbol] = now

        return task

    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            queued: _QueuedTask | None = None
            with self._lock:
                if (
                    self._pending_queue
                    and len(self._running_task_ids) < self.settings.task_max_concurrency
                ):
                    queued = self._pending_queue.popleft()
                    self._running_task_ids.add(queued.task_id)

            if queued is not None:
                self._executor.submit(self._run_task, queued)
            else:
                time.sleep(0.05)

    def _run_task(self, queued: _QueuedTask) -> None:
        self.repository.update_task(queued.task_id, TaskStatus.PENDING)
        inc_analysis_task(TaskStatus.PENDING.value)

        self.repository.update_task(queued.task_id, TaskStatus.RUNNING)
        inc_analysis_task(TaskStatus.RUNNING.value)

        logger.info(
            "Task started task_id=%s request_id=%s symbols=%s",
            queued.task_id,
            queued.request_id,
            queued.symbols,
        )

        try:
            future = self._pipeline_executor.submit(
                self.pipeline.run,
                task_id=queued.task_id,
                symbols=queued.symbols,
                force_refresh=queued.force_refresh,
                skip_market_guard=queued.skip_market_guard,
            )
            future.result(timeout=self.settings.task_timeout_seconds)
            self.repository.update_task(queued.task_id, TaskStatus.COMPLETED)
            inc_analysis_task(TaskStatus.COMPLETED.value)
        except FutureTimeoutError:
            message = f"Task timeout after {self.settings.task_timeout_seconds}s"
            self.repository.update_task(
                queued.task_id, TaskStatus.FAILED, error=message
            )
            inc_analysis_task(TaskStatus.FAILED.value)
            cancelled = future.cancel()
            logger.error(
                "Task timed out task_id=%s request_id=%s timeout=%s cancelled=%s",
                queued.task_id,
                queued.request_id,
                self.settings.task_timeout_seconds,
                cancelled,
            )
        except Exception as exc:  # noqa: BLE001
            self.repository.update_task(
                queued.task_id, TaskStatus.FAILED, error=str(exc)
            )
            inc_analysis_task(TaskStatus.FAILED.value)
            logger.exception(
                "Task failed task_id=%s request_id=%s error=%s",
                queued.task_id,
                queued.request_id,
                exc,
            )
        finally:
            with self._lock:
                self._running_task_ids.discard(queued.task_id)

    def _prune_recent_submissions(self, now: float) -> None:
        if self.settings.task_dedup_window_seconds <= 0:
            self._recent_symbol_submissions.clear()
            return
        ttl = float(self.settings.task_dedup_window_seconds)
        expired = [
            symbol
            for symbol, timestamp in self._recent_symbol_submissions.items()
            if now - timestamp > ttl
        ]
        for symbol in expired:
            self._recent_symbol_submissions.pop(symbol, None)

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        return self.repository.list_tasks(limit=limit)

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.repository.get_task(task_id)

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._dispatcher.is_alive():
            self._dispatcher.join(timeout=1)
        self._executor.shutdown(wait=False, cancel_futures=False)
        self._pipeline_executor.shutdown(wait=False, cancel_futures=False)
