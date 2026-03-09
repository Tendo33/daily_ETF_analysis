from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from daily_etf_analysis.domain import AnalysisTask, TaskStatus, normalize_symbol
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline
from daily_etf_analysis.repositories import EtfRepository


class TaskManager:
    def __init__(self, repository: EtfRepository, pipeline: DailyPipeline) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="etf-analysis"
        )
        self._lock = threading.Lock()
        self._inflight_symbols: set[str] = set()

    def submit(self, symbols: list[str], force_refresh: bool = False) -> AnalysisTask:
        normalized_symbols = [normalize_symbol(s) for s in symbols]
        with self._lock:
            duplicates = self._inflight_symbols.intersection(normalized_symbols)
            if duplicates:
                joined = ", ".join(sorted(duplicates))
                raise ValueError(f"Task already running for symbols: {joined}")
            self._inflight_symbols.update(normalized_symbols)

        task = AnalysisTask(
            task_id=uuid.uuid4().hex,
            status=TaskStatus.PENDING,
            symbols=normalized_symbols,
            force_refresh=force_refresh,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.repository.create_task(task)
        self._executor.submit(
            self._run_task, task.task_id, normalized_symbols, force_refresh
        )
        return task

    def _run_task(self, task_id: str, symbols: list[str], force_refresh: bool) -> None:
        self.repository.update_task(task_id, TaskStatus.RUNNING)
        try:
            self.pipeline.run(
                task_id=task_id, symbols=symbols, force_refresh=force_refresh
            )
            self.repository.update_task(task_id, TaskStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001
            self.repository.update_task(task_id, TaskStatus.FAILED, error=str(exc))
        finally:
            with self._lock:
                for symbol in symbols:
                    self._inflight_symbols.discard(symbol)

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        return self.repository.list_tasks(limit=limit)

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.repository.get_task(task_id)
