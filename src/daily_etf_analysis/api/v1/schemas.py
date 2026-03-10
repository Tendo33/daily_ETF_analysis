from __future__ import annotations

from datetime import date, datetime
from typing import Any

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


class HistoryListItemResponse(BaseModel):
    id: int
    task_id: str
    symbol: str
    trade_date: str
    score: int
    action: str
    confidence: str
    summary: str
    success: bool
    created_at: str


class HistoryListResponse(BaseModel):
    items: list[HistoryListItemResponse]
    page: int
    limit: int
    total: int


class HistoryDetailResponse(BaseModel):
    id: int
    task_id: str
    symbol: str
    trade_date: str
    score: int
    trend: str
    action: str
    confidence: str
    summary: str
    model_used: str | None = None
    success: bool
    error_message: str | None = None
    factors: dict[str, Any]
    key_points: list[str]
    risk_alerts: list[str]
    context_snapshot: dict[str, Any]
    news_items: list[dict[str, Any]]
    created_at: str


class BacktestRunRequest(BaseModel):
    symbols: list[str] | None = None
    eval_window_days: int = Field(default=20, ge=1, le=365)


class BacktestResultRowResponse(BaseModel):
    symbol: str
    sample_count: int = 0
    evaluated_count: int = 0
    skipped_count: int = 0
    direction_hit_rate: float | None = None
    avg_return: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = None


class BacktestRunSummaryResponse(BaseModel):
    run_id: str
    eval_window_days: int
    total_samples: int
    evaluated_samples: int
    skipped_count: int
    direction_hit_rate: float | None = None
    avg_return: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = None
    disclaimer: str


class BacktestRunResponse(BaseModel):
    run: BacktestRunSummaryResponse
    results: list[BacktestResultRowResponse]


class BacktestPerformanceResponse(BaseModel):
    run_id: str
    direction_hit_rate: float | None = None
    avg_return: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = None
    disclaimer: str


class SystemConfigResponse(BaseModel):
    version: int
    config: dict[str, Any]


class SystemConfigValidateRequest(BaseModel):
    updates: dict[str, Any]


class SystemConfigIssueResponse(BaseModel):
    severity: str
    field: str
    message: str


class SystemConfigValidateResponse(BaseModel):
    valid: bool
    issues: list[SystemConfigIssueResponse]
    candidate_config: dict[str, Any]


class SystemConfigUpdateRequest(BaseModel):
    expected_version: int = Field(ge=0)
    updates: dict[str, Any]


class SystemConfigSchemaResponse(BaseModel):
    fields: dict[str, dict[str, Any]]


class SystemConfigAuditItemResponse(BaseModel):
    id: int
    version: int
    actor: str
    action: str
    changes: dict[str, Any]
    created_at: str
