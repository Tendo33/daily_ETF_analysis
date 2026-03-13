from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class AnalysisRunCreateRequest(BaseModel):
    symbols: list[str] | None = None
    markets: list[str] | None = None
    force_refresh: bool = False
    force_retry: bool = False
    source: str = "api"
    run_window: str | None = None


class AnalysisRunCreateResponse(BaseModel):
    run_id: str
    status: str


class AnalysisRunDetailResponse(BaseModel):
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


class ReplaceEtfsRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class ReplaceIndexMappingsRequest(BaseModel):
    mappings: dict[str, list[str]]


class DailyReportResponse(BaseModel):
    run_summary: dict[str, Any]
    symbol_results: list[dict[str, Any]]
    decision_quality: dict[str, Any]
    failures: list[dict[str, Any]]
    global_summary_text: str | None = None


class HistorySignalsResponse(BaseModel):
    items: list[dict[str, Any]]


class ErrorDetailResponse(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class HistorySignalsQuery(BaseModel):
    symbol: str | None = None
    run_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=200, ge=1, le=2000)


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


class LifecycleCleanupResponse(BaseModel):
    dry_run: bool
    actor: str
    executed_at: str
    retention_days: dict[str, int]
    impacted: dict[str, int]
    deleted: dict[str, int]
