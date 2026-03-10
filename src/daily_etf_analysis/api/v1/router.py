from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from daily_etf_analysis.api.auth import require_admin_token
from daily_etf_analysis.api.v1.schemas import (
    BacktestPerformanceResponse,
    BacktestResultRowResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    HistoryDetailResponse,
    HistoryListResponse,
    IndexComparisonResponse,
    IndexComparisonRowResponse,
    ProviderHealthResponse,
    ReplaceEtfsRequest,
    ReplaceIndexMappingsRequest,
    RunAnalysisRequest,
    RunAnalysisResponse,
    SystemConfigAuditItemResponse,
    SystemConfigResponse,
    SystemConfigSchemaResponse,
    SystemConfigUpdateRequest,
    SystemConfigValidateRequest,
    SystemConfigValidateResponse,
    TaskResponse,
)
from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.domain import normalize_symbol
from daily_etf_analysis.services import AnalysisService

router = APIRouter(prefix="/api/v1")


@lru_cache
def _service() -> AnalysisService:
    return AnalysisService()


@router.post("/analysis/run", response_model=RunAnalysisResponse)
def run_analysis(
    request: RunAnalysisRequest, _: None = Depends(require_admin_token)
) -> RunAnalysisResponse:
    settings = get_settings()
    symbols = request.symbols
    if not symbols and request.markets:
        allowed_markets = {m.lower() for m in request.markets}
        symbols = [
            symbol
            for symbol in settings.etf_list
            if symbol.split(":", 1)[0].lower() in allowed_markets
        ]
    task = _service().run_analysis(symbols=symbols, force_refresh=request.force_refresh)
    return RunAnalysisResponse(task_id=task.task_id, status=task.status.value)


@router.get("/analysis/tasks", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=50, ge=1, le=200)) -> list[TaskResponse]:
    tasks = _service().list_tasks(limit=limit)
    return [
        TaskResponse(
            task_id=t.task_id,
            status=t.status.value,
            symbols=t.symbols,
            force_refresh=t.force_refresh,
            created_at=t.created_at,
            updated_at=t.updated_at,
            error=t.error,
        )
        for t in tasks
    ]


@router.get("/analysis/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = _service().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return TaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        symbols=task.symbols,
        force_refresh=task.force_refresh,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error,
    )


@router.get("/history", response_model=HistoryListResponse)
def list_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    symbol: str | None = Query(default=None),
) -> HistoryListResponse:
    try:
        payload = _service().list_history(page=page, limit=limit, symbol=symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return HistoryListResponse.model_validate(payload)


@router.get("/history/{record_id}", response_model=HistoryDetailResponse)
def get_history_detail(record_id: int) -> HistoryDetailResponse:
    item = _service().get_history_detail(record_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"History record not found: {record_id}"
        )
    return HistoryDetailResponse.model_validate(item)


@router.get("/history/{record_id}/news")
def get_history_news(record_id: int) -> list[dict[str, object]]:
    items = _service().get_history_news(record_id)
    if items is None:
        raise HTTPException(
            status_code=404, detail=f"History record not found: {record_id}"
        )
    return items


@router.post("/backtest/run", response_model=BacktestRunResponse)
def run_backtest(
    request: BacktestRunRequest, _: None = Depends(require_admin_token)
) -> BacktestRunResponse:
    try:
        payload = _service().run_backtest(
            symbols=request.symbols, eval_window_days=request.eval_window_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BacktestRunResponse.model_validate(payload)


@router.get("/backtest/results", response_model=list[BacktestResultRowResponse])
def get_backtest_results(
    run_id: str = Query(min_length=1),
) -> list[BacktestResultRowResponse]:
    rows = _service().get_backtest_results(run_id)
    if rows is None:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")
    return [BacktestResultRowResponse.model_validate(row) for row in rows]


@router.get("/backtest/performance", response_model=BacktestPerformanceResponse)
def get_backtest_performance(
    run_id: str = Query(min_length=1),
) -> BacktestPerformanceResponse:
    run = _service().get_backtest_performance(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")
    return BacktestPerformanceResponse(
        run_id=str(run["run_id"]),
        direction_hit_rate=_to_float(run.get("direction_hit_rate")),
        avg_return=_to_float(run.get("avg_return")),
        max_drawdown=_to_float(run.get("max_drawdown")),
        win_rate=_to_float(run.get("win_rate")),
        disclaimer=str(
            run.get("disclaimer", "For research only; not investment advice.")
        ),
    )


@router.get("/backtest/performance/{symbol}", response_model=BacktestResultRowResponse)
def get_backtest_symbol_performance(
    symbol: str, run_id: str = Query(min_length=1)
) -> BacktestResultRowResponse:
    try:
        row = _service().get_backtest_symbol_performance(run_id=run_id, symbol=symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Backtest record not found: run_id={run_id}, symbol={symbol}",
        )
    return BacktestResultRowResponse.model_validate(row)


@router.get("/etfs")
def list_etfs() -> list[dict[str, object]]:
    items = _service().list_etfs()
    return [
        {
            "symbol": i.symbol,
            "market": i.market.value,
            "code": i.code,
            "name": i.name,
            "benchmark_index": i.benchmark_index,
            "currency": i.currency,
            "enabled": i.enabled,
            "updated_at": i.updated_at.isoformat(),
        }
        for i in items
    ]


@router.put("/etfs")
def replace_etfs(
    request: ReplaceEtfsRequest, _: None = Depends(require_admin_token)
) -> list[dict[str, object]]:
    items = _service().replace_etfs(request.symbols)
    return [
        {
            "symbol": i.symbol,
            "market": i.market.value,
            "code": i.code,
            "name": i.name,
            "benchmark_index": i.benchmark_index,
            "currency": i.currency,
            "enabled": i.enabled,
            "updated_at": i.updated_at.isoformat(),
        }
        for i in items
    ]


@router.get("/index-mappings")
def get_index_mappings() -> dict[str, list[str]]:
    return _service().get_index_mappings()


@router.put("/index-mappings")
def replace_index_mappings(
    request: ReplaceIndexMappingsRequest, _: None = Depends(require_admin_token)
) -> dict[str, list[str]]:
    return _service().replace_index_mappings(request.mappings)


@router.get("/etfs/{symbol}/quote")
def get_quote(symbol: str) -> dict[str, str | float | None]:
    try:
        return _service().get_quote(normalize_symbol(symbol))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/etfs/{symbol}/history")
def get_history(
    symbol: str, days: int = Query(default=120, ge=1, le=3650)
) -> list[dict[str, str | float | None]]:
    try:
        return _service().get_history(normalize_symbol(symbol), days=days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports/daily")
def get_daily_report(
    date_str: str = Query(alias="date"), market: str = Query(default="all")
) -> list[dict[str, object]]:
    report_date = date.fromisoformat(date_str)
    return _service().get_daily_report(report_date, market=market)


@router.get("/index-comparisons", response_model=IndexComparisonResponse)
def get_index_comparisons(
    index_symbol: Annotated[str, Query(min_length=1)],
    target_date: Annotated[date | None, Query(alias="date")] = None,
) -> IndexComparisonResponse:
    try:
        result = _service().get_index_comparison(
            index_symbol=index_symbol, target_date=target_date
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IndexComparisonResponse(
        index_symbol=result.index_symbol,
        report_date=result.report_date,
        rows=[
            IndexComparisonRowResponse(
                symbol=row.symbol,
                market=row.market,
                score=row.score,
                action=row.action,
                confidence=row.confidence,
                latest_price=row.latest_price,
                change_pct=row.change_pct,
                return_20=row.return_20,
                return_60=row.return_60,
                rank=row.rank,
                model_used=row.model_used,
                success=row.success,
            )
            for row in result.rows
        ],
    )


@router.get("/system/provider-health", response_model=list[ProviderHealthResponse])
def get_provider_health() -> list[ProviderHealthResponse]:
    items = _service().get_provider_health()
    return [ProviderHealthResponse.model_validate(item) for item in items]


@router.get("/system/config", response_model=SystemConfigResponse)
def get_system_config() -> SystemConfigResponse:
    payload = _service().get_system_config()
    return SystemConfigResponse.model_validate(payload)


@router.post(
    "/system/config/validate",
    response_model=SystemConfigValidateResponse,
)
def validate_system_config(
    request: SystemConfigValidateRequest, _: None = Depends(require_admin_token)
) -> SystemConfigValidateResponse:
    payload = _service().validate_system_config(request.updates)
    return SystemConfigValidateResponse.model_validate(payload)


@router.put("/system/config", response_model=SystemConfigResponse)
def update_system_config(
    request: SystemConfigUpdateRequest, _: None = Depends(require_admin_token)
) -> SystemConfigResponse:
    try:
        payload = _service().update_system_config(
            expected_version=request.expected_version,
            updates=request.updates,
            actor="admin",
        )
    except ValueError as exc:
        detail = str(exc)
        if detail.startswith("version_conflict:"):
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc
    return SystemConfigResponse.model_validate(payload)


@router.get("/system/config/schema", response_model=SystemConfigSchemaResponse)
def get_system_config_schema() -> SystemConfigSchemaResponse:
    payload = _service().get_system_config_schema()
    return SystemConfigSchemaResponse.model_validate(payload)


@router.get(
    "/system/config/audit",
    response_model=list[SystemConfigAuditItemResponse],
)
def list_system_config_audit(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[SystemConfigAuditItemResponse]:
    rows = _service().list_system_config_audit(page=page, limit=limit)
    return [SystemConfigAuditItemResponse.model_validate(row) for row in rows]


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
