from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from daily_etf_analysis.domain import AnalysisRun


class RunDetailContract(BaseModel):
    run_id: str
    status: str
    source: str
    market: str
    run_window: str | None = None
    symbols: list[str]
    created_at: str
    updated_at: str
    completed_at: str | None = None
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    decision_quality: dict[str, Any]
    failures: list[dict[str, Any]]
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)


class RunSummaryContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None
    date: str
    market: str
    total_symbols: int
    generated_at: str


class SymbolResultContract(BaseModel):
    run_id: str | None
    task_id: str | None = None
    symbol: str
    trade_date: str | None = None
    score: int | None = None
    trend: str | None = None
    action: str | None = None
    confidence: str | None = None
    horizon: str
    risk_alerts: list[object] = Field(default_factory=list)
    rationale: str = ""
    degraded: bool = False
    fallback_reason: str | None = None


class DecisionQualityContract(BaseModel):
    total: int
    degraded_count: int
    fallback_count: int
    success_rate: float


class DailyReportContract(BaseModel):
    run_summary: RunSummaryContract
    symbol_results: list[SymbolResultContract]
    decision_quality: DecisionQualityContract
    failures: list[dict[str, Any]] = Field(default_factory=list)


def build_run_detail_contract(
    *,
    run: AnalysisRun,
    failures: list[dict[str, Any]],
    audit_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    return RunDetailContract(
        run_id=run.run_id,
        status=run.status.value,
        source=run.source,
        market=run.market,
        run_window=run.run_window,
        symbols=run.symbols,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        total_tasks=run.total_tasks,
        completed_tasks=run.completed_tasks,
        failed_tasks=run.failed_tasks,
        cancelled_tasks=run.cancelled_tasks,
        decision_quality=run.decision_quality,
        failures=failures,
        audit_logs=audit_logs,
    ).model_dump()


def build_daily_report_contract(
    *,
    target_date: date,
    market: str,
    report_rows: list[dict[str, Any]],
    run_id: str | None = None,
    failures: list[dict[str, Any]] | None = None,
    generated_at: date | None = None,
    run_summary_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filtered = [
        row for row in report_rows if run_id is None or row.get("run_id") == run_id
    ]
    symbol_results = [
        SymbolResultContract(
            run_id=row.get("run_id"),
            task_id=row.get("task_id"),
            symbol=str(row.get("symbol", "")),
            trade_date=_format_date(row.get("trade_date")),
            score=_to_int_or_none(row.get("score")),
            trend=_to_str_or_none(row.get("trend")),
            action=_to_str_or_none(row.get("action")),
            confidence=_to_str_or_none(row.get("confidence")),
            horizon=str(row.get("horizon") or "next_trading_day"),
            risk_alerts=list(row.get("risk_alerts") or []),
            rationale=str(row.get("rationale") or row.get("summary", "")),
            degraded=bool(row.get("degraded", False)),
            fallback_reason=_to_str_or_none(row.get("fallback_reason")),
        )
        for row in filtered
    ]
    total = len(symbol_results)
    degraded_count = sum(1 for item in symbol_results if item.degraded)
    success_count = total - degraded_count
    run_summary = RunSummaryContract(
        run_id=run_id,
        date=target_date.isoformat(),
        market=market,
        total_symbols=total,
        generated_at=(generated_at or date.today()).isoformat(),
        **(run_summary_extra or {}),
    )
    contract = DailyReportContract(
        run_summary=run_summary,
        symbol_results=symbol_results,
        decision_quality=DecisionQualityContract(
            total=total,
            degraded_count=degraded_count,
            fallback_count=degraded_count,
            success_rate=(success_count / total) if total else 0.0,
        ),
        failures=failures or [],
    )
    return contract.model_dump()


def _format_date(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def _to_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _to_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
