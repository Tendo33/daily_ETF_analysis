from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from daily_etf_analysis.api.v1.schemas import (
    ReplaceEtfsRequest,
    ReplaceIndexMappingsRequest,
    RunAnalysisRequest,
    RunAnalysisResponse,
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
def run_analysis(request: RunAnalysisRequest) -> RunAnalysisResponse:
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
def replace_etfs(request: ReplaceEtfsRequest) -> list[dict[str, object]]:
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
    request: ReplaceIndexMappingsRequest,
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
