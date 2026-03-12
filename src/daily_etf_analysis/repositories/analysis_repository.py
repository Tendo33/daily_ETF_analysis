from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import desc, func, select

from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    AnalysisRun,
    AnalysisTask,
    EtfAnalysisResult,
    TaskErrorCode,
    TaskStatus,
    parse_task_status,
)
from daily_etf_analysis.repositories.models import (
    AnalysisRunAuditLogORM,
    AnalysisRunORM,
    AnalysisTaskORM,
    EtfAnalysisReportORM,
    EtfRealtimeQuoteORM,
)
from daily_etf_analysis.repositories.shared import parse_task_error_code


class AnalysisRepositoryMixin:
    def session(self) -> Any:
        raise NotImplementedError

    def create_task(self, task: AnalysisTask) -> None:
        with self.session() as db:
            db.add(
                AnalysisTaskORM(
                    task_id=task.task_id,
                    status=task.status.value,
                    symbols_json=json.dumps(task.symbols, ensure_ascii=False),
                    force_refresh=task.force_refresh,
                    run_id=task.run_id,
                    error=task.error,
                    error_code=task.error_code.value,
                    skip_reason=task.skip_reason,
                    skipped_symbols_json=json.dumps(
                        task.skipped_symbols, ensure_ascii=False
                    ),
                    analyzed_count=task.analyzed_count,
                    skipped_count=task.skipped_count,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
            )

    def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
        error_code: TaskErrorCode = TaskErrorCode.NONE,
        skip_reason: str | None = None,
        skipped_symbols: list[str] | None = None,
        analyzed_count: int | None = None,
        skipped_count: int | None = None,
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id)
            ).scalar_one()
            row.status = status.value
            row.error = error
            row.error_code = error_code.value
            row.skip_reason = skip_reason
            if skipped_symbols is not None:
                row.skipped_symbols_json = json.dumps(
                    skipped_symbols, ensure_ascii=False
                )
            if analyzed_count is not None:
                row.analyzed_count = analyzed_count
            if skipped_count is not None:
                row.skipped_count = skipped_count
            row.updated_at = utc_now_naive()

    def get_task(self, task_id: str) -> AnalysisTask | None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return AnalysisTask(
                task_id=row.task_id,
                status=parse_task_status(row.status),
                symbols=json.loads(row.symbols_json),
                force_refresh=row.force_refresh,
                run_id=row.run_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                error=row.error,
                error_code=parse_task_error_code(row.error_code),
                skip_reason=row.skip_reason,
                skipped_symbols=json.loads(row.skipped_symbols_json or "[]"),
                analyzed_count=row.analyzed_count,
                skipped_count=row.skipped_count,
            )

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(AnalysisTaskORM)
                    .order_by(desc(AnalysisTaskORM.updated_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                AnalysisTask(
                    task_id=row.task_id,
                    status=parse_task_status(row.status),
                    symbols=json.loads(row.symbols_json),
                    force_refresh=row.force_refresh,
                    run_id=row.run_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    error=row.error,
                    error_code=parse_task_error_code(row.error_code),
                    skip_reason=row.skip_reason,
                    skipped_symbols=json.loads(row.skipped_symbols_json or "[]"),
                    analyzed_count=row.analyzed_count,
                    skipped_count=row.skipped_count,
                )
                for row in rows
            ]

    def count_active_tasks(self) -> int:
        with self.session() as db:
            return int(
                db.execute(
                    select(func.count())
                    .select_from(AnalysisTaskORM)
                    .where(
                        AnalysisTaskORM.status.in_(
                            [
                                TaskStatus.PENDING.value,
                                TaskStatus.PROCESSING.value,
                            ]
                        )
                    )
                ).scalar()
                or 0
            )

    def create_analysis_run(
        self,
        *,
        run_id: str,
        symbols: list[str],
        source: str,
        market: str,
        run_window: str | None,
    ) -> None:
        with self.session() as db:
            db.add(
                AnalysisRunORM(
                    run_id=run_id,
                    status=TaskStatus.PENDING.value,
                    symbols_json=json.dumps(symbols, ensure_ascii=False),
                    source=source,
                    market=market,
                    run_window=run_window,
                    total_tasks=len(symbols),
                    completed_tasks=0,
                    failed_tasks=0,
                    cancelled_tasks=0,
                    decision_quality_json="{}",
                    failure_summary_json="{}",
                    created_at=utc_now_naive(),
                    updated_at=utc_now_naive(),
                )
            )

    def create_analysis_run_with_tasks(
        self,
        *,
        run_id: str,
        symbols: list[str],
        source: str,
        market: str,
        run_window: str | None,
        tasks: list[AnalysisTask],
        audit_payload: dict[str, Any],
    ) -> None:
        with self.session() as db:
            db.add(
                AnalysisRunORM(
                    run_id=run_id,
                    status=TaskStatus.PROCESSING.value,
                    symbols_json=json.dumps(symbols, ensure_ascii=False),
                    source=source,
                    market=market,
                    run_window=run_window,
                    total_tasks=len(symbols),
                    completed_tasks=0,
                    failed_tasks=0,
                    cancelled_tasks=0,
                    decision_quality_json="{}",
                    failure_summary_json="{}",
                    created_at=utc_now_naive(),
                    updated_at=utc_now_naive(),
                )
            )
            db.add(
                AnalysisRunAuditLogORM(
                    run_id=run_id,
                    event_type="run_created",
                    payload_json=json.dumps(audit_payload, ensure_ascii=False),
                    created_at=utc_now_naive(),
                )
            )
            for task in tasks:
                db.add(
                    AnalysisTaskORM(
                        task_id=task.task_id,
                        status=task.status.value,
                        symbols_json=json.dumps(task.symbols, ensure_ascii=False),
                        force_refresh=task.force_refresh,
                        run_id=task.run_id,
                        error=task.error,
                        error_code=task.error_code.value,
                        skip_reason=task.skip_reason,
                        skipped_symbols_json=json.dumps(
                            task.skipped_symbols, ensure_ascii=False
                        ),
                        analyzed_count=task.analyzed_count,
                        skipped_count=task.skipped_count,
                        created_at=task.created_at,
                        updated_at=task.updated_at,
                    )
                )

    def create_analysis_run_failure(
        self,
        *,
        run_id: str,
        symbols: list[str],
        source: str,
        market: str,
        run_window: str | None,
        error: str,
        request_id: str | None,
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisRunORM).where(AnalysisRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                row = AnalysisRunORM(
                    run_id=run_id,
                    status=TaskStatus.FAILED.value,
                    symbols_json=json.dumps(symbols, ensure_ascii=False),
                    source=source,
                    market=market,
                    run_window=run_window,
                    total_tasks=len(symbols),
                    completed_tasks=0,
                    failed_tasks=0,
                    cancelled_tasks=0,
                    decision_quality_json="{}",
                    failure_summary_json="{}",
                    created_at=utc_now_naive(),
                    updated_at=utc_now_naive(),
                    completed_at=utc_now_naive(),
                )
                db.add(row)
            else:
                row.status = TaskStatus.FAILED.value
                row.updated_at = utc_now_naive()
                row.completed_at = utc_now_naive()
            db.add(
                AnalysisRunAuditLogORM(
                    run_id=run_id,
                    event_type="run_failed",
                    payload_json=json.dumps(
                        {
                            "error": error,
                            "request_id": request_id,
                        },
                        ensure_ascii=False,
                    ),
                    created_at=utc_now_naive(),
                )
            )

    def set_analysis_run_status(self, run_id: str, status: TaskStatus) -> None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisRunORM).where(AnalysisRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return
            row.status = status.value
            row.updated_at = utc_now_naive()
            if status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                row.completed_at = utc_now_naive()

    def update_analysis_run_quality(
        self,
        run_id: str,
        *,
        decision_quality: dict[str, Any],
        failure_summary: dict[str, Any],
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisRunORM).where(AnalysisRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return
            row.decision_quality_json = json.dumps(decision_quality, ensure_ascii=False)
            row.failure_summary_json = json.dumps(failure_summary, ensure_ascii=False)
            row.updated_at = utc_now_naive()

    def refresh_analysis_run_from_tasks(self, run_id: str) -> None:
        with self.session() as db:
            run = db.execute(
                select(AnalysisRunORM).where(AnalysisRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if run is None:
                return
            rows = (
                db.execute(
                    select(AnalysisTaskORM).where(AnalysisTaskORM.run_id == run_id)
                )
                .scalars()
                .all()
            )
            total = len(rows)
            completed = sum(
                1 for item in rows if item.status == TaskStatus.COMPLETED.value
            )
            failed = sum(1 for item in rows if item.status == TaskStatus.FAILED.value)
            cancelled = sum(
                1 for item in rows if item.status == TaskStatus.CANCELLED.value
            )
            run.total_tasks = total
            run.completed_tasks = completed
            run.failed_tasks = failed
            run.cancelled_tasks = cancelled
            if total == 0:
                run.status = TaskStatus.PENDING.value
            elif completed + failed + cancelled == total:
                if failed > 0:
                    run.status = TaskStatus.FAILED.value
                elif cancelled > 0 and completed == 0:
                    run.status = TaskStatus.CANCELLED.value
                else:
                    run.status = TaskStatus.COMPLETED.value
                run.completed_at = utc_now_naive()
            else:
                run.status = TaskStatus.PROCESSING.value
            run.updated_at = utc_now_naive()

    def get_analysis_run(self, run_id: str) -> AnalysisRun | None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisRunORM).where(AnalysisRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return AnalysisRun(
                run_id=row.run_id,
                status=parse_task_status(row.status),
                symbols=json.loads(row.symbols_json or "[]"),
                source=row.source,
                market=row.market,
                run_window=row.run_window,
                created_at=row.created_at,
                updated_at=row.updated_at,
                completed_at=row.completed_at,
                total_tasks=row.total_tasks,
                completed_tasks=row.completed_tasks,
                failed_tasks=row.failed_tasks,
                cancelled_tasks=row.cancelled_tasks,
                decision_quality=json.loads(row.decision_quality_json or "{}"),
                failure_summary=json.loads(row.failure_summary_json or "{}"),
            )

    def list_tasks_by_run(self, run_id: str) -> list[AnalysisTask]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(AnalysisTaskORM)
                    .where(AnalysisTaskORM.run_id == run_id)
                    .order_by(desc(AnalysisTaskORM.created_at))
                )
                .scalars()
                .all()
            )
            return [
                AnalysisTask(
                    task_id=row.task_id,
                    status=parse_task_status(row.status),
                    symbols=json.loads(row.symbols_json or "[]"),
                    force_refresh=row.force_refresh,
                    run_id=row.run_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    error=row.error,
                    error_code=parse_task_error_code(row.error_code),
                    skip_reason=row.skip_reason,
                    skipped_symbols=json.loads(row.skipped_symbols_json or "[]"),
                    analyzed_count=row.analyzed_count,
                    skipped_count=row.skipped_count,
                )
                for row in rows
            ]

    def create_analysis_run_audit_log(
        self, *, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        with self.session() as db:
            db.add(
                AnalysisRunAuditLogORM(
                    run_id=run_id,
                    event_type=event_type,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=utc_now_naive(),
                )
            )

    def list_analysis_run_audit_logs(
        self, run_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(AnalysisRunAuditLogORM)
                    .where(AnalysisRunAuditLogORM.run_id == run_id)
                    .order_by(desc(AnalysisRunAuditLogORM.id))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "event_type": row.event_type,
                    "payload": json.loads(row.payload_json or "{}"),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def save_analysis_report(
        self,
        task_id: str,
        symbol: str,
        trade_date: date,
        factors: dict[str, Any],
        result: EtfAnalysisResult,
        run_id: str | None = None,
        context_snapshot: dict[str, Any] | None = None,
        news_items: list[dict[str, Any]] | None = None,
    ) -> None:
        with self.session() as db:
            db.add(
                EtfAnalysisReportORM(
                    run_id=run_id,
                    task_id=task_id,
                    symbol=symbol,
                    trade_date=trade_date,
                    score=result.score,
                    trend=result.trend.value,
                    action=result.action.value,
                    confidence=result.confidence.value,
                    summary=result.summary,
                    model_used=result.model_used,
                    success=result.success,
                    error_message=result.error_message,
                    horizon=result.horizon,
                    rationale=result.rationale,
                    degraded=result.degraded,
                    fallback_reason=result.fallback_reason,
                    factors_json=json.dumps(factors, ensure_ascii=False),
                    key_points_json=json.dumps(result.key_points, ensure_ascii=False),
                    risk_alerts_json=json.dumps(result.risk_alerts, ensure_ascii=False),
                    context_snapshot_json=json.dumps(
                        context_snapshot or {}, ensure_ascii=False
                    ),
                    news_items_json=json.dumps(news_items or [], ensure_ascii=False),
                    created_at=utc_now_naive(),
                )
            )

    def list_history(
        self, page: int = 1, limit: int = 20, symbol: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        offset = max(0, (page - 1) * limit)
        with self.session() as db:
            query = select(EtfAnalysisReportORM)
            count_query = select(func.count()).select_from(EtfAnalysisReportORM)
            if symbol:
                normalized = symbol.upper()
                query = query.where(EtfAnalysisReportORM.symbol == normalized)
                count_query = count_query.where(
                    EtfAnalysisReportORM.symbol == normalized
                )
            total = int(db.execute(count_query).scalar() or 0)
            rows = (
                db.execute(
                    query.order_by(
                        desc(EtfAnalysisReportORM.trade_date),
                        desc(EtfAnalysisReportORM.id),
                    )
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            items = [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "task_id": row.task_id,
                    "symbol": row.symbol,
                    "trade_date": row.trade_date.isoformat(),
                    "score": row.score,
                    "action": row.action,
                    "confidence": row.confidence,
                    "summary": row.summary,
                    "success": row.success,
                    "degraded": row.degraded,
                    "fallback_reason": row.fallback_reason,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
            return items, total

    def get_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                select(EtfAnalysisReportORM).where(EtfAnalysisReportORM.id == record_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "run_id": row.run_id,
                "task_id": row.task_id,
                "symbol": row.symbol,
                "trade_date": row.trade_date.isoformat(),
                "score": row.score,
                "trend": row.trend,
                "action": row.action,
                "confidence": row.confidence,
                "summary": row.summary,
                "horizon": row.horizon,
                "rationale": row.rationale,
                "model_used": row.model_used,
                "success": row.success,
                "degraded": row.degraded,
                "fallback_reason": row.fallback_reason,
                "error_message": row.error_message,
                "factors": json.loads(row.factors_json),
                "key_points": json.loads(row.key_points_json),
                "risk_alerts": json.loads(row.risk_alerts_json),
                "context_snapshot": json.loads(row.context_snapshot_json),
                "news_items": json.loads(row.news_items_json),
                "created_at": row.created_at.isoformat(),
            }

    def get_history_news(self, record_id: int) -> list[dict[str, Any]]:
        record = self.get_history_record(record_id)
        if not record:
            return []
        value = record.get("news_items", [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def get_daily_reports(
        self, report_date: date, market: str | None = None
    ) -> list[dict[str, Any]]:
        with self.session() as db:
            query = select(EtfAnalysisReportORM).where(
                EtfAnalysisReportORM.trade_date == report_date
            )
            if market:
                query = query.where(
                    EtfAnalysisReportORM.symbol.like(f"{market.upper()}:%")
                )
            rows = (
                db.execute(query.order_by(EtfAnalysisReportORM.symbol)).scalars().all()
            )
            result = []
            for row in rows:
                result.append(
                    {
                        "task_id": row.task_id,
                        "run_id": row.run_id,
                        "symbol": row.symbol,
                        "trade_date": row.trade_date.isoformat(),
                        "score": row.score,
                        "trend": row.trend,
                        "action": row.action,
                        "confidence": row.confidence,
                        "summary": row.summary,
                        "horizon": row.horizon,
                        "rationale": row.rationale,
                        "model_used": row.model_used,
                        "success": row.success,
                        "degraded": row.degraded,
                        "fallback_reason": row.fallback_reason,
                        "error_message": row.error_message,
                        "factors": json.loads(row.factors_json),
                        "key_points": json.loads(row.key_points_json),
                        "risk_alerts": json.loads(row.risk_alerts_json),
                    }
                )
            return result

    def get_recent_signals(
        self, symbols: list[str], limit: int
    ) -> dict[str, list[dict[str, Any]]]:
        if not symbols or limit <= 0:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            try:
                ranked = (
                    select(
                        EtfAnalysisReportORM.symbol.label("symbol"),
                        EtfAnalysisReportORM.trade_date.label("trade_date"),
                        EtfAnalysisReportORM.action.label("action"),
                        EtfAnalysisReportORM.trend.label("trend"),
                        EtfAnalysisReportORM.score.label("score"),
                        func.row_number()
                        .over(
                            partition_by=EtfAnalysisReportORM.symbol,
                            order_by=(
                                desc(EtfAnalysisReportORM.trade_date),
                                desc(EtfAnalysisReportORM.id),
                            ),
                        )
                        .label("row_num"),
                    )
                    .where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                    .subquery()
                )
                rows = db.execute(
                    select(ranked)
                    .where(ranked.c.row_num <= limit)
                    .order_by(
                        ranked.c.symbol,
                        ranked.c.row_num,
                    )
                ).all()
                results: dict[str, list[dict[str, Any]]] = {}
                for row in rows:
                    bucket = results.setdefault(str(row.symbol), [])
                    trade_date = row.trade_date
                    bucket.append(
                        {
                            "trade_date": (
                                trade_date.isoformat()
                                if isinstance(trade_date, date)
                                else str(trade_date)
                            ),
                            "action": str(row.action),
                            "trend": str(row.trend),
                            "score": int(row.score),
                        }
                    )
                return results
            except Exception:
                rows = (
                    db.execute(
                        select(EtfAnalysisReportORM)
                        .where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                        .order_by(
                            EtfAnalysisReportORM.symbol,
                            desc(EtfAnalysisReportORM.trade_date),
                            desc(EtfAnalysisReportORM.id),
                        )
                    )
                    .scalars()
                    .all()
                )
                fallback_results: dict[str, list[dict[str, Any]]] = {
                    s: [] for s in normalized_symbols
                }
                for row in rows:
                    bucket = fallback_results.setdefault(row.symbol, [])
                    if len(bucket) >= limit:
                        continue
                    bucket.append(
                        {
                            "trade_date": row.trade_date.isoformat(),
                            "action": row.action,
                            "trend": row.trend,
                            "score": row.score,
                        }
                    )
                return {k: v for k, v in fallback_results.items() if v}

    def list_signals_v2(
        self,
        *,
        symbol: str | None = None,
        run_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self.session() as db:
            query = select(EtfAnalysisReportORM)
            if symbol:
                query = query.where(EtfAnalysisReportORM.symbol == symbol.upper())
            if run_id:
                query = query.where(EtfAnalysisReportORM.run_id == run_id)
            if date_from:
                query = query.where(EtfAnalysisReportORM.trade_date >= date_from)
            if date_to:
                query = query.where(EtfAnalysisReportORM.trade_date <= date_to)
            rows = (
                db.execute(
                    query.order_by(
                        desc(EtfAnalysisReportORM.trade_date),
                        desc(EtfAnalysisReportORM.id),
                    ).limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "run_id": row.run_id,
                    "task_id": row.task_id,
                    "symbol": row.symbol,
                    "trade_date": row.trade_date.isoformat(),
                    "score": row.score,
                    "trend": row.trend,
                    "action": row.action,
                    "confidence": row.confidence,
                    "horizon": row.horizon,
                    "rationale": row.rationale,
                    "risk_alerts": json.loads(row.risk_alerts_json),
                    "summary": row.summary,
                    "degraded": row.degraded,
                    "fallback_reason": row.fallback_reason,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def list_failures_by_run(self, run_id: str) -> list[dict[str, Any]]:
        tasks = self.list_tasks_by_run(run_id)
        rows: list[dict[str, Any]] = []
        for task in tasks:
            if task.status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "task_id": task.task_id,
                    "symbols": task.symbols,
                    "error_code": task.error_code.value,
                    "error_message": task.error,
                    "skip_reason": task.skip_reason,
                    "updated_at": task.updated_at.isoformat(),
                }
            )
        return rows

    def get_latest_report_trade_date_for_task(self, task_id: str) -> date | None:
        with self.session() as db:
            return (
                db.execute(
                    select(EtfAnalysisReportORM.trade_date)
                    .where(EtfAnalysisReportORM.task_id == task_id)
                    .order_by(desc(EtfAnalysisReportORM.trade_date))
                    .limit(1)
                )
                .scalars()
                .first()
            )

    def get_latest_reports_for_symbols(
        self, symbols: list[str], report_date: date | None = None
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            base_query = select(EtfAnalysisReportORM).where(
                EtfAnalysisReportORM.symbol.in_(normalized_symbols)
            )
            if report_date is not None:
                base_query = base_query.where(
                    EtfAnalysisReportORM.trade_date == report_date
                )
            try:
                ranked = select(
                    EtfAnalysisReportORM.id.label("id"),
                    EtfAnalysisReportORM.symbol.label("symbol"),
                    func.row_number()
                    .over(
                        partition_by=EtfAnalysisReportORM.symbol,
                        order_by=(
                            desc(EtfAnalysisReportORM.trade_date),
                            desc(EtfAnalysisReportORM.id),
                        ),
                    )
                    .label("row_num"),
                ).where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                if report_date is not None:
                    ranked = ranked.where(
                        EtfAnalysisReportORM.trade_date == report_date
                    )
                ranked_subquery = ranked.subquery()
                latest_ids = (
                    db.execute(
                        select(ranked_subquery.c.id).where(
                            ranked_subquery.c.row_num == 1
                        )
                    )
                    .scalars()
                    .all()
                )
                if not latest_ids:
                    return {}
                rows = (
                    db.execute(
                        select(EtfAnalysisReportORM).where(
                            EtfAnalysisReportORM.id.in_(latest_ids)
                        )
                    )
                    .scalars()
                    .all()
                )
            except Exception:
                rows = (
                    db.execute(
                        base_query.order_by(
                            EtfAnalysisReportORM.symbol,
                            desc(EtfAnalysisReportORM.trade_date),
                            desc(EtfAnalysisReportORM.id),
                        )
                    )
                    .scalars()
                    .all()
                )
            latest: dict[str, dict[str, Any]] = {}
            for row in rows:
                if row.symbol in latest:
                    continue
                latest[row.symbol] = {
                    "symbol": row.symbol,
                    "trade_date": row.trade_date,
                    "score": row.score,
                    "trend": row.trend,
                    "action": row.action,
                    "confidence": row.confidence,
                    "summary": row.summary,
                    "horizon": row.horizon,
                    "rationale": row.rationale,
                    "model_used": row.model_used,
                    "success": row.success,
                    "degraded": row.degraded,
                    "fallback_reason": row.fallback_reason,
                    "error_message": row.error_message,
                    "factors": json.loads(row.factors_json),
                    "key_points": json.loads(row.key_points_json),
                    "risk_alerts": json.loads(row.risk_alerts_json),
                }
            return latest

    def count_expired_records(
        self,
        *,
        task_created_before: datetime,
        report_created_before: datetime,
        quote_time_before: datetime,
    ) -> dict[str, int]:
        with self.session() as db:
            task_count = int(
                db.execute(
                    select(func.count())
                    .select_from(AnalysisTaskORM)
                    .where(AnalysisTaskORM.created_at < task_created_before)
                ).scalar()
                or 0
            )
            report_count = int(
                db.execute(
                    select(func.count())
                    .select_from(EtfAnalysisReportORM)
                    .where(EtfAnalysisReportORM.created_at < report_created_before)
                ).scalar()
                or 0
            )
            quote_count = int(
                db.execute(
                    select(func.count())
                    .select_from(EtfRealtimeQuoteORM)
                    .where(EtfRealtimeQuoteORM.quote_time < quote_time_before)
                ).scalar()
                or 0
            )
            return {
                "tasks": task_count,
                "reports": report_count,
                "quotes": quote_count,
            }

    def delete_expired_records(
        self,
        *,
        task_created_before: datetime,
        report_created_before: datetime,
        quote_time_before: datetime,
    ) -> dict[str, int]:
        with self.session() as db:
            deleted_tasks = (
                db.query(AnalysisTaskORM)
                .filter(AnalysisTaskORM.created_at < task_created_before)
                .delete()
            )
            deleted_reports = (
                db.query(EtfAnalysisReportORM)
                .filter(EtfAnalysisReportORM.created_at < report_created_before)
                .delete()
            )
            deleted_quotes = (
                db.query(EtfRealtimeQuoteORM)
                .filter(EtfRealtimeQuoteORM.quote_time < quote_time_before)
                .delete()
            )
            return {
                "tasks": int(deleted_tasks),
                "reports": int(deleted_reports),
                "quotes": int(deleted_quotes),
            }
