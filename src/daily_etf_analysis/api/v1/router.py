from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from daily_etf_analysis.api.auth import require_admin_token
from daily_etf_analysis.api.v1.schemas import (
    AnalysisRunCreateRequest,
    AnalysisRunCreateResponse,
    AnalysisRunDetailResponse,
    BacktestPerformanceResponse,
    BacktestResultRowResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    DailyReportResponse,
    HistorySignalsResponse,
    IndexComparisonResponse,
    IndexComparisonRowResponse,
    LifecycleCleanupResponse,
    ProviderHealthResponse,
    ReplaceEtfsRequest,
    ReplaceIndexMappingsRequest,
    SystemConfigAuditItemResponse,
    SystemConfigResponse,
    SystemConfigSchemaResponse,
    SystemConfigUpdateRequest,
    SystemConfigValidateRequest,
    SystemConfigValidateResponse,
)
from daily_etf_analysis.domain import normalize_symbol
from daily_etf_analysis.services import AnalysisService

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_admin_token)])


@lru_cache
def _service() -> AnalysisService:
    return AnalysisService()


@router.post(
    "/analysis/runs", response_model=AnalysisRunCreateResponse, status_code=202
)
def create_run(
    request: AnalysisRunCreateRequest,
    http_request: Request,
) -> AnalysisRunCreateResponse:
    try:
        run = _service().create_analysis_run(
            symbols=request.symbols,
            markets=request.markets,
            force_refresh=request.force_refresh,
            force_retry=request.force_retry,
            source=request.source,
            request_id=getattr(http_request.state, "request_id", None),
            run_window=request.run_window,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_RUN_REQUEST",
                message="Invalid analysis run request.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
    return AnalysisRunCreateResponse(run_id=run.run_id, status=run.status.value)


@router.get("/analysis/runs/{run_id}", response_model=AnalysisRunDetailResponse)
def get_run(run_id: str, http_request: Request) -> AnalysisRunDetailResponse:
    payload = _service().build_run_contract(run_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="RUN_NOT_FOUND",
                message="Analysis run not found.",
                request=http_request,
                details={"run_id": run_id},
            ),
        )
    return AnalysisRunDetailResponse.model_validate(payload)


@router.get("/reports/daily", response_model=DailyReportResponse)
def get_daily_report(
    http_request: Request,
    date_str: str = Query(alias="date"),
    market: str = Query(default="all"),
    run_id: str | None = Query(default=None),
) -> DailyReportResponse:
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_DATE",
                message="Date must be in YYYY-MM-DD format.",
                request=http_request,
            ),
        ) from exc
    payload = _service().get_daily_report_contract(
        target_date=target_date,
        market=market,
        run_id=run_id,
    )
    return DailyReportResponse.model_validate(payload)


@router.get("/history/signals", response_model=HistorySignalsResponse)
def list_history_signals(
    http_request: Request,
    symbol: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: int = Query(default=200, ge=1, le=2000),
) -> HistorySignalsResponse:
    try:
        rows = _service().list_history_signals(
            symbol=symbol,
            run_id=run_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_HISTORY_QUERY",
                message="Invalid history query parameters.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
    return HistorySignalsResponse(items=rows)


@router.post("/backtest/run", response_model=BacktestRunResponse)
def run_backtest(
    request: BacktestRunRequest,
    http_request: Request,
) -> BacktestRunResponse:
    try:
        payload = _service().run_backtest(
            symbols=request.symbols,
            eval_window_days=request.eval_window_days,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_BACKTEST_REQUEST",
                message="Invalid backtest request.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
    return BacktestRunResponse.model_validate(payload)


@router.get("/backtest/results", response_model=list[BacktestResultRowResponse])
def get_backtest_results(
    http_request: Request,
    run_id: str = Query(min_length=1),
) -> list[BacktestResultRowResponse]:
    rows = _service().get_backtest_results(run_id)
    if rows is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="BACKTEST_RUN_NOT_FOUND",
                message="Backtest run not found.",
                request=http_request,
                details={"run_id": run_id},
            ),
        )
    return [BacktestResultRowResponse.model_validate(row) for row in rows]


@router.get("/backtest/performance", response_model=BacktestPerformanceResponse)
def get_backtest_performance(
    http_request: Request,
    run_id: str = Query(min_length=1),
) -> BacktestPerformanceResponse:
    run = _service().get_backtest_performance(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="BACKTEST_RUN_NOT_FOUND",
                message="Backtest run not found.",
                request=http_request,
                details={"run_id": run_id},
            ),
        )
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
    http_request: Request,
    symbol: str,
    run_id: str = Query(min_length=1),
) -> BacktestResultRowResponse:
    try:
        row = _service().get_backtest_symbol_performance(run_id=run_id, symbol=symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_SYMBOL",
                message="Invalid symbol.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="BACKTEST_RECORD_NOT_FOUND",
                message="Backtest record not found.",
                request=http_request,
                details={"run_id": run_id, "symbol": symbol},
            ),
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
    request: ReplaceEtfsRequest,
    http_request: Request,
) -> list[dict[str, object]]:
    try:
        items = _service().replace_etfs(request.symbols)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_SYMBOL",
                message="Invalid symbol.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
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
    request: ReplaceIndexMappingsRequest,
    http_request: Request,
) -> dict[str, list[str]]:
    try:
        return _service().replace_index_mappings(request.mappings)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_INDEX_MAPPING",
                message="Invalid index mappings.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc


@router.get("/etfs/{symbol}/quote")
def get_quote(
    symbol: str,
    http_request: Request,
) -> dict[str, str | float | None]:
    try:
        return _service().get_quote(normalize_symbol(symbol))
    except ValueError as exc:
        detail = str(exc).lower()
        if "valid market" in detail or "unable to infer market" in detail:
            raise HTTPException(
                status_code=422,
                detail=_error_detail(
                    code="INVALID_SYMBOL",
                    message="Invalid symbol.",
                    request=http_request,
                ),
            ) from exc
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="QUOTE_NOT_FOUND",
                message="Quote not found.",
                request=http_request,
                details={"symbol": symbol},
            ),
        ) from exc


@router.get("/etfs/{symbol}/history")
def get_history(
    http_request: Request,
    symbol: str,
    days: int = Query(default=120, ge=1, le=3650),
) -> list[dict[str, str | float | None]]:
    try:
        return _service().get_history(normalize_symbol(symbol), days=days)
    except ValueError as exc:
        detail = str(exc).lower()
        if "valid market" in detail or "unable to infer market" in detail:
            raise HTTPException(
                status_code=422,
                detail=_error_detail(
                    code="INVALID_SYMBOL",
                    message="Invalid symbol.",
                    request=http_request,
                ),
            ) from exc
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="HISTORY_NOT_FOUND",
                message="History not found.",
                request=http_request,
                details={"symbol": symbol},
            ),
        ) from exc


@router.get("/index-comparisons", response_model=IndexComparisonResponse)
def get_index_comparisons(
    http_request: Request,
    index_symbol: Annotated[str, Query(min_length=1)],
    target_date: Annotated[date | None, Query(alias="date")] = None,
) -> IndexComparisonResponse:
    try:
        result = _service().get_index_comparison(
            index_symbol=index_symbol,
            target_date=target_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_detail(
                code="INDEX_MAPPING_NOT_FOUND",
                message="No mapping found for index symbol.",
                request=http_request,
                details={"index_symbol": index_symbol},
            ),
        ) from exc
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


@router.post("/system/config/validate", response_model=SystemConfigValidateResponse)
def validate_system_config(
    request: SystemConfigValidateRequest,
) -> SystemConfigValidateResponse:
    payload = _service().validate_system_config(request.updates)
    return SystemConfigValidateResponse.model_validate(payload)


@router.put("/system/config", response_model=SystemConfigResponse)
def update_system_config(
    request: SystemConfigUpdateRequest,
    http_request: Request,
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
            raise HTTPException(
                status_code=409,
                detail=_error_detail(
                    code="CONFIG_VERSION_CONFLICT",
                    message="Config version conflict.",
                    request=http_request,
                ),
            ) from exc
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                code="INVALID_CONFIG_UPDATE",
                message="Invalid config update.",
                request=http_request,
                details={"reason": str(exc)},
            ),
        ) from exc
    return SystemConfigResponse.model_validate(payload)


@router.get("/system/config/schema", response_model=SystemConfigSchemaResponse)
def get_system_config_schema() -> SystemConfigSchemaResponse:
    payload = _service().get_system_config_schema()
    return SystemConfigSchemaResponse.model_validate(payload)


@router.get("/system/config/audit", response_model=list[SystemConfigAuditItemResponse])
def list_system_config_audit(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[SystemConfigAuditItemResponse]:
    rows = _service().list_system_config_audit(page=page, limit=limit)
    return [SystemConfigAuditItemResponse.model_validate(row) for row in rows]


@router.post("/system/lifecycle/cleanup", response_model=LifecycleCleanupResponse)
def run_lifecycle_cleanup(
    dry_run: bool = Query(default=True),
) -> LifecycleCleanupResponse:
    payload = _service().cleanup_data_lifecycle(dry_run=dry_run, actor="admin")
    return LifecycleCleanupResponse.model_validate(payload)


def shutdown_service() -> None:
    cache_info = getattr(_service, "cache_info", None)
    if not callable(cache_info):
        return
    if cache_info().currsize == 0:
        return
    _service().shutdown()
    cache_clear = getattr(_service, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


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


def _error_detail(
    *,
    code: str,
    message: str,
    request: Request | None,
    details: dict[str, object] | None = None,
) -> dict[str, object | None]:
    request_id = None
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
        if request_id is not None:
            request_id = str(request_id)
    return {
        "code": code,
        "message": message,
        "request_id": request_id,
        "details": details,
    }
