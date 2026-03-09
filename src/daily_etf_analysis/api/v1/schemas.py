from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class RunAnalysisRequest(BaseModel):
    symbols: list[str] | None = None
    markets: list[str] | None = None
    force_refresh: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: str
    symbols: list[str]
    force_refresh: bool
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class RunAnalysisResponse(BaseModel):
    task_id: str
    status: str


class ReplaceEtfsRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class ReplaceIndexMappingsRequest(BaseModel):
    mappings: dict[str, list[str]]


class DailyReportQuery(BaseModel):
    date: date
    market: str = "all"


class IndexComparisonRowResponse(BaseModel):
    symbol: str
    market: str
    score: int
    action: str
    confidence: str
    latest_price: float | None = None
    change_pct: float | None = None
    return_20: float | None = None
    return_60: float | None = None
    rank: int
    model_used: str | None = None
    success: bool


class IndexComparisonResponse(BaseModel):
    index_symbol: str
    report_date: date
    rows: list[IndexComparisonRowResponse]


class ProviderHealthResponse(BaseModel):
    provider: str
    operation: str
    success_count: int
    failure_count: int
    retry_count: int
    circuit_state: str
    last_error: str | None = None
    last_updated: str
