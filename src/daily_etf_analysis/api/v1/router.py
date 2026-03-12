from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from daily_etf_analysis.api.auth import require_admin_token
from daily_etf_analysis.api.runtime import AppRuntime
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


def _get_service(request: Request) -> AnalysisService:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        runtime = AppRuntime()
        request.app.state.runtime = runtime
    return runtime.get_service()


ServiceDep = Annotated[AnalysisService, Depends(_get_service)]


@router.post(
    "/analysis/runs", response_model=AnalysisRunCreateResponse, status_code=202
)
def create_run(
    request: AnalysisRunCreateRequest,
    http_request: Request,
    service: ServiceDep,
) -> AnalysisRunCreateResponse:
    try:
        run = service.create_analysis_run(
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
def get_run(
    run_id: str,
    http_request: Request,
    service: ServiceDep,
) -> AnalysisRunDetailResponse:
    payload = service.build_run_contract(run_id)
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


@router.post(
    "/analysis/runs/{run_id}/refresh", response_model=AnalysisRunDetailResponse
)
def refresh_run(
    run_id: str,
    http_request: Request,
    service: ServiceDep,
) -> AnalysisRunDetailResponse:
    payload = service.refresh_analysis_run(run_id)
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
    service: ServiceDep,
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
    payload = service.get_daily_report_contract(
        target_date=target_date,
        market=market,
        run_id=run_id,
    )
    return DailyReportResponse.model_validate(payload)


@router.get("/history/signals", response_model=HistorySignalsResponse)
def list_history_signals(
    http_request: Request,
    service: ServiceDep,
    symbol: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: int = Query(default=200, ge=1, le=2000),
) -> HistorySignalsResponse:
    try:
        rows = service.list_history_signals(
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
    service: ServiceDep,
) -> BacktestRunResponse:
    try:
        payload = service.run_backtest(
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
    service: ServiceDep,
    run_id: str = Query(min_length=1),
) -> list[BacktestResultRowResponse]:
    rows = service.get_backtest_results(run_id)
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
    service: ServiceDep,
    run_id: str = Query(min_length=1),
) -> BacktestPerformanceResponse:
    run = service.get_backtest_performance(run_id)
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
    service: ServiceDep,
    run_id: str = Query(min_length=1),
) -> BacktestResultRowResponse:
    try:
        row = service.get_backtest_symbol_performance(run_id=run_id, symbol=symbol)
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
def list_etfs(
    service: ServiceDep,
) -> list[dict[str, object]]:
    items = service.list_etfs()
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
    service: ServiceDep,
) -> list[dict[str, object]]:
    try:
        items = service.replace_etfs(request.symbols)
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
def get_index_mappings(
    service: ServiceDep,
) -> dict[str, list[str]]:
    return service.get_index_mappings()


@router.put("/index-mappings")
def replace_index_mappings(
    request: ReplaceIndexMappingsRequest,
    http_request: Request,
    service: ServiceDep,
) -> dict[str, list[str]]:
    try:
        return service.replace_index_mappings(request.mappings)
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
    service: ServiceDep,
) -> dict[str, str | float | None]:
    try:
        return service.get_quote(normalize_symbol(symbol))
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
    service: ServiceDep,
    days: int = Query(default=120, ge=1, le=3650),
) -> list[dict[str, str | float | None]]:
    try:
        return service.get_history(normalize_symbol(symbol), days=days)
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
    service: ServiceDep,
    target_date: Annotated[date | None, Query(alias="date")] = None,
) -> IndexComparisonResponse:
    try:
        result = service.get_index_comparison(
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
def get_provider_health(
    service: ServiceDep,
) -> list[ProviderHealthResponse]:
    items = service.get_provider_health()
    return [ProviderHealthResponse.model_validate(item) for item in items]


@router.get("/system/config", response_model=SystemConfigResponse)
def get_system_config(
    service: ServiceDep,
) -> SystemConfigResponse:
    payload = service.get_system_config()
    return SystemConfigResponse.model_validate(payload)


@router.post("/system/config/validate", response_model=SystemConfigValidateResponse)
def validate_system_config(
    request: SystemConfigValidateRequest,
    service: ServiceDep,
) -> SystemConfigValidateResponse:
    payload = service.validate_system_config(request.updates)
    return SystemConfigValidateResponse.model_validate(payload)


@router.put("/system/config", response_model=SystemConfigResponse)
def update_system_config(
    request: SystemConfigUpdateRequest,
    http_request: Request,
    service: ServiceDep,
) -> SystemConfigResponse:
    try:
        payload = service.update_system_config(
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
def get_system_config_schema(
    service: ServiceDep,
) -> SystemConfigSchemaResponse:
    payload = service.get_system_config_schema()
    return SystemConfigSchemaResponse.model_validate(payload)


@router.get("/system/config/audit", response_model=list[SystemConfigAuditItemResponse])
def list_system_config_audit(
    service: ServiceDep,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[SystemConfigAuditItemResponse]:
    rows = service.list_system_config_audit(page=page, limit=limit)
    return [SystemConfigAuditItemResponse.model_validate(row) for row in rows]


@router.post("/system/lifecycle/cleanup", response_model=LifecycleCleanupResponse)
def run_lifecycle_cleanup(
    service: ServiceDep,
    dry_run: bool = Query(default=True),
) -> LifecycleCleanupResponse:
    payload = service.cleanup_data_lifecycle(dry_run=dry_run, actor="admin")
    return LifecycleCleanupResponse.model_validate(payload)


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
