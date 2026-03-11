from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    AnalysisTask,
    TaskErrorCode,
    TaskStatus,
    normalize_symbol,
)
from daily_etf_analysis.observability import inc_analysis_task
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline
from daily_etf_analysis.repositories import EtfRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _QueuedTask:
    task_id: str
    symbol: str
    force_refresh: bool
    skip_market_guard: bool
    request_id: str | None
    run_id: str | None
    run_window: str | None
    cancel_event: threading.Event


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
        self._subscriber_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pending_queue: deque[_QueuedTask] = deque()
        self._running_task_ids: set[str] = set()
        self._active_symbol_tasks: dict[str, str] = {}
        self._task_symbols: dict[str, str] = {}
        self._timed_out_futures: dict[str, Future[object]] = {}
        self._run_window_task_ids: dict[str, set[str]] = {}
        self._task_run_window: dict[str, str] = {}
        self._subscribers: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, object]]]
        ] = []

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
        force_retry: bool = False,
        run_id: str | None = None,
        run_window: str | None = None,
    ) -> AnalysisTask:
        tasks = self.submit_many(
            symbols=symbols,
            force_refresh=force_refresh,
            skip_market_guard=skip_market_guard,
            request_id=request_id,
            force_retry=force_retry,
            run_id=run_id,
            run_window=run_window,
        )
        return tasks[0]

    def submit_many(
        self,
        symbols: list[str],
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        request_id: str | None = None,
        force_retry: bool = False,
        run_id: str | None = None,
        run_window: str | None = None,
    ) -> list[AnalysisTask]:
        normalized_symbols = list(dict.fromkeys(normalize_symbol(s) for s in symbols))
        if not normalized_symbols:
            raise ValueError("No symbols provided")

        tasks: list[AnalysisTask] = []
        with self._lock:
            if run_window and not force_retry:
                active_window_tasks = self._run_window_task_ids.get(run_window, set())
                if active_window_tasks:
                    raise ValueError(f"Run window lock active: {run_window}")
            if not force_retry:
                dedup_hits = [
                    symbol
                    for symbol in normalized_symbols
                    if self._symbol_is_active(symbol)
                ]
                if dedup_hits:
                    joined = ", ".join(sorted(set(dedup_hits)))
                    raise ValueError(f"Task dedup hit for active symbols: {joined}")

            for symbol in normalized_symbols:
                task = AnalysisTask(
                    task_id=uuid.uuid4().hex,
                    status=TaskStatus.PENDING,
                    symbols=[symbol],
                    force_refresh=force_refresh,
                    run_id=run_id,
                    created_at=utc_now_naive(),
                    updated_at=utc_now_naive(),
                )
                self.repository.create_task(task)
                self._pending_queue.append(
                    _QueuedTask(
                        task_id=task.task_id,
                        symbol=symbol,
                        force_refresh=force_refresh,
                        skip_market_guard=skip_market_guard,
                        request_id=request_id,
                        run_id=run_id,
                        run_window=run_window,
                        cancel_event=threading.Event(),
                    )
                )
                self._task_symbols[task.task_id] = symbol
                self._active_symbol_tasks[symbol] = task.task_id
                if run_window:
                    bucket = self._run_window_task_ids.setdefault(run_window, set())
                    bucket.add(task.task_id)
                    self._task_run_window[task.task_id] = run_window
                tasks.append(task)

        for task in tasks:
            inc_analysis_task(TaskStatus.PENDING.value)
            self._broadcast_event("task_created", self._task_payload(task))
        return tasks

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
        self.repository.update_task(queued.task_id, TaskStatus.PROCESSING)
        inc_analysis_task(TaskStatus.PROCESSING.value)
        self._emit_task_event("task_started", queued.task_id)

        logger.info(
            "Task started task_id=%s request_id=%s symbol=%s",
            queued.task_id,
            queued.request_id,
            queued.symbol,
        )
        if queued.run_id:
            self.repository.create_analysis_run_audit_log(
                run_id=queued.run_id,
                event_type="task_started",
                payload={"task_id": queued.task_id, "symbol": queued.symbol},
            )

        future: Future[object] | None = None
        keep_symbol_active = False
        try:
            future = self._pipeline_executor.submit(
                self.pipeline.run,
                task_id=queued.task_id,
                symbols=[queued.symbol],
                run_id=queued.run_id,
                force_refresh=queued.force_refresh,
                skip_market_guard=queued.skip_market_guard,
                cancel_event=queued.cancel_event,
            )
            result = future.result(timeout=self.settings.task_timeout_seconds)
            analyzed_count = 0
            skipped_count = 0
            skipped_symbols: list[str] = []
            skip_reason: str | None = None
            if isinstance(result, list):
                analyzed_count = len(result)
            else:
                analyzed_count = int(getattr(result, "analyzed_count", 0))
                skipped_count = int(getattr(result, "skipped_count", 0))
                raw_symbols = getattr(result, "skipped_symbols", [])
                if isinstance(raw_symbols, list):
                    skipped_symbols = [str(item) for item in raw_symbols]
                raw_reason = getattr(result, "skip_reason", None)
                skip_reason = str(raw_reason) if raw_reason else None

            if skip_reason and "cancelled" in skip_reason.lower():
                self.repository.update_task(
                    queued.task_id,
                    TaskStatus.CANCELLED,
                    error=skip_reason,
                    error_code=TaskErrorCode.TASK_CANCELLED,
                    analyzed_count=analyzed_count,
                    skipped_count=skipped_count,
                    skipped_symbols=skipped_symbols,
                    skip_reason=skip_reason,
                )
                inc_analysis_task(TaskStatus.CANCELLED.value)
                self._emit_task_event("task_cancelled", queued.task_id)
                if queued.run_id:
                    self.repository.create_analysis_run_audit_log(
                        run_id=queued.run_id,
                        event_type="task_cancelled",
                        payload={
                            "task_id": queued.task_id,
                            "symbol": queued.symbol,
                            "reason": skip_reason,
                        },
                    )
            else:
                self.repository.update_task(
                    queued.task_id,
                    TaskStatus.COMPLETED,
                    error_code=TaskErrorCode.NONE,
                    analyzed_count=analyzed_count,
                    skipped_count=skipped_count,
                    skipped_symbols=skipped_symbols,
                    skip_reason=skip_reason,
                )
                inc_analysis_task(TaskStatus.COMPLETED.value)
                self._emit_task_event("task_completed", queued.task_id)
                if queued.run_id:
                    self.repository.create_analysis_run_audit_log(
                        run_id=queued.run_id,
                        event_type="task_completed",
                        payload={
                            "task_id": queued.task_id,
                            "symbol": queued.symbol,
                            "analyzed_count": analyzed_count,
                            "skipped_count": skipped_count,
                        },
                    )
        except FutureTimeoutError:
            message = (
                f"TASK_TIMEOUT after {self.settings.task_timeout_seconds}s "
                f"(request_id={queued.request_id or 'unknown'})"
            )
            queued.cancel_event.set()
            cancelled = False
            if future is not None:
                cancelled = future.cancel()
                if not cancelled:
                    with self._lock:
                        self._timed_out_futures[queued.task_id] = future
                    keep_symbol_active = True
            self.repository.update_task(
                queued.task_id,
                TaskStatus.FAILED,
                error=message,
                error_code=TaskErrorCode.TASK_TIMEOUT,
                analyzed_count=0,
                skipped_count=0,
            )
            inc_analysis_task(TaskStatus.FAILED.value)
            self._emit_task_event("task_failed", queued.task_id)
            if queued.run_id:
                self.repository.create_analysis_run_audit_log(
                    run_id=queued.run_id,
                    event_type="task_failed",
                    payload={
                        "task_id": queued.task_id,
                        "symbol": queued.symbol,
                        "error_code": TaskErrorCode.TASK_TIMEOUT.value,
                        "error": message,
                    },
                )
            logger.error(
                "Task timed out task_id=%s request_id=%s timeout=%s cancelled=%s error_code=TASK_TIMEOUT",
                queued.task_id,
                queued.request_id,
                self.settings.task_timeout_seconds,
                cancelled,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"TASK_EXEC_FAILED (request_id={queued.request_id or 'unknown'})"
            self.repository.update_task(
                queued.task_id,
                TaskStatus.FAILED,
                error=message,
                error_code=TaskErrorCode.TASK_EXEC_FAILED,
                analyzed_count=0,
                skipped_count=0,
            )
            inc_analysis_task(TaskStatus.FAILED.value)
            self._emit_task_event("task_failed", queued.task_id)
            if queued.run_id:
                self.repository.create_analysis_run_audit_log(
                    run_id=queued.run_id,
                    event_type="task_failed",
                    payload={
                        "task_id": queued.task_id,
                        "symbol": queued.symbol,
                        "error_code": TaskErrorCode.TASK_EXEC_FAILED.value,
                        "error": message,
                    },
                )
            logger.exception(
                "Task failed task_id=%s request_id=%s error_code=TASK_EXEC_FAILED error=%s",
                queued.task_id,
                queued.request_id,
                exc,
            )
        finally:
            with self._lock:
                self._running_task_ids.discard(queued.task_id)
                if not keep_symbol_active:
                    self._timed_out_futures.pop(queued.task_id, None)
                    self._clear_active_symbol_locked(queued.task_id)
                    self._clear_run_window_locked(queued.task_id)
            if queued.run_id:
                self.repository.refresh_analysis_run_from_tasks(queued.run_id)

    def _symbol_is_active(self, symbol: str) -> bool:
        task_id = self._active_symbol_tasks.get(symbol)
        if task_id is None:
            return False
        return self._task_is_active(task_id)

    def _clear_active_symbol_locked(self, task_id: str) -> None:
        symbol = self._task_symbols.pop(task_id, None)
        if symbol is None:
            return
        if self._active_symbol_tasks.get(symbol) == task_id:
            self._active_symbol_tasks.pop(symbol, None)

    def _clear_run_window_locked(self, task_id: str) -> None:
        run_window = self._task_run_window.pop(task_id, None)
        if run_window is None:
            return
        bucket = self._run_window_task_ids.get(run_window)
        if bucket is None:
            return
        bucket.discard(task_id)
        if not bucket:
            self._run_window_task_ids.pop(run_window, None)

    def _task_is_active(self, task_id: str) -> bool:
        timed_out_future = self._timed_out_futures.get(task_id)
        if timed_out_future is not None:
            if not timed_out_future.done():
                return True
            self._timed_out_futures.pop(task_id, None)
            self._clear_active_symbol_locked(task_id)
            self._clear_run_window_locked(task_id)

        task = self.repository.get_task(task_id)
        if task is not None and task.status not in {
            TaskStatus.PENDING,
            TaskStatus.PROCESSING,
        }:
            return False
        if task_id in self._running_task_ids:
            return True
        if any(item.task_id == task_id for item in self._pending_queue):
            return True
        if task is None:
            return False
        return task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        return self.repository.list_tasks(limit=limit)

    def list_pending_tasks(self, limit: int = 200) -> list[AnalysisTask]:
        tasks = self.repository.list_tasks(limit=limit)
        return [
            task
            for task in tasks
            if task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}
        ]

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.repository.get_task(task_id)

    def subscribe(self, event_queue: asyncio.Queue[dict[str, object]]) -> None:
        loop = asyncio.get_running_loop()
        with self._subscriber_lock:
            self._subscribers.append((loop, event_queue))

    def unsubscribe(self, event_queue: asyncio.Queue[dict[str, object]]) -> None:
        with self._subscriber_lock:
            self._subscribers = [
                (loop, queue)
                for loop, queue in self._subscribers
                if queue is not event_queue
            ]

    def _emit_task_event(self, event_type: str, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if task is None:
            return
        self._broadcast_event(event_type, self._task_payload(task))

    def _broadcast_event(self, event_type: str, data: dict[str, object]) -> None:
        with self._subscriber_lock:
            subscribers = list(self._subscribers)
        event: dict[str, object] = {"type": event_type, "data": data}
        for loop, event_queue in subscribers:
            try:

                def _enqueue(
                    queue: asyncio.Queue[dict[str, object]] = event_queue,
                    payload: dict[str, object] = event,
                ) -> None:
                    queue.put_nowait(payload)

                loop.call_soon_threadsafe(_enqueue)
            except RuntimeError:
                continue

    @staticmethod
    def _task_payload(task: AnalysisTask) -> dict[str, object]:
        return {
            "task_id": task.task_id,
            "run_id": task.run_id,
            "status": task.status.value,
            "symbols": list(task.symbols),
            "force_refresh": task.force_refresh,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "error": task.error,
            "error_code": task.error_code.value,
            "skip_reason": task.skip_reason,
            "skipped_symbols": list(task.skipped_symbols),
            "analyzed_count": task.analyzed_count,
            "skipped_count": task.skipped_count,
        }

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._dispatcher.is_alive():
            self._dispatcher.join(timeout=1)
        self._executor.shutdown(wait=False, cancel_futures=False)
        self._pipeline_executor.shutdown(wait=False, cancel_futures=False)
