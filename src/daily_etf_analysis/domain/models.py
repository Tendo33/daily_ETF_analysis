from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain.enums import (
    Action,
    Confidence,
    Market,
    TaskErrorCode,
    TaskStatus,
    Trend,
)


@dataclass(slots=True)
class EtfInstrument:
    symbol: str
    market: Market
    code: str
    name: str = ""
    benchmark_index: str = ""
    currency: str = ""
    enabled: bool = True
    updated_at: datetime = field(default_factory=utc_now_naive)


@dataclass(slots=True)
class EtfDailyBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None
    pct_chg: float | None = None
    source: str = ""


@dataclass(slots=True)
class EtfRealtimeQuote:
    symbol: str
    price: float
    change_pct: float | None = None
    turnover: float | None = None
    volume: float | None = None
    amount: float | None = None
    quote_time: datetime = field(default_factory=utc_now_naive)
    source: str = ""


@dataclass(slots=True)
class EtfAnalysisContext:
    symbol: str
    market: Market
    code: str
    benchmark_index: str
    factors: dict[str, Any]
    latest_quote: EtfRealtimeQuote | None = None
    latest_bar: EtfDailyBar | None = None
    news_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EtfAnalysisResult:
    symbol: str
    score: int
    trend: Trend
    action: Action
    confidence: Confidence
    summary: str
    name: str | None = None
    key_points: list[str] = field(default_factory=list)
    risk_alerts: list[str] = field(default_factory=list)
    model_used: str | None = None
    success: bool = True
    error_message: str | None = None
    raw_response: str | None = None
    horizon: str = "next_trading_day"
    rationale: str = ""
    degraded: bool = False
    fallback_reason: str | None = None
    operation_advice: str | None = None
    analysis_summary: str | None = None
    trend_prediction: str | None = None
    decision_type: str | None = None
    confidence_level: str | None = None
    dashboard: dict[str, Any] | None = None
    llm_payload: dict[str, Any] | None = None
    market_snapshot: dict[str, Any] | None = None

    @classmethod
    def neutral_fallback(cls, symbol: str, error_message: str) -> EtfAnalysisResult:
        return cls(
            symbol=symbol,
            name=symbol,
            score=50,
            trend=Trend.NEUTRAL,
            action=Action.HOLD,
            confidence=Confidence.LOW,
            summary="LLM analysis unavailable; using neutral fallback.",
            key_points=["Neutral fallback used due to LLM failure."],
            risk_alerts=[],
            model_used=None,
            success=False,
            error_message=error_message,
            horizon="next_trading_day",
            rationale="Fallback to neutral recommendation due to unavailable model output.",
            degraded=True,
            fallback_reason="NEUTRAL_FALLBACK",
            operation_advice="观望",
            analysis_summary="LLM analysis unavailable; using neutral fallback.",
            trend_prediction="震荡",
            decision_type="hold",
            confidence_level="低",
            dashboard={},
            llm_payload={},
            market_snapshot={},
        )


@dataclass(slots=True)
class AnalysisTask:
    task_id: str
    status: TaskStatus
    symbols: list[str]
    force_refresh: bool
    run_id: str | None = None
    created_at: datetime = field(default_factory=utc_now_naive)
    updated_at: datetime = field(default_factory=utc_now_naive)
    error: str | None = None
    error_code: TaskErrorCode = TaskErrorCode.NONE
    skip_reason: str | None = None
    skipped_symbols: list[str] = field(default_factory=list)
    analyzed_count: int = 0
    skipped_count: int = 0


@dataclass(slots=True)
class AnalysisRun:
    run_id: str
    status: TaskStatus
    symbols: list[str]
    source: str = "manual"
    market: str = "all"
    run_window: str | None = None
    created_at: datetime = field(default_factory=utc_now_naive)
    updated_at: datetime = field(default_factory=utc_now_naive)
    completed_at: datetime | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    decision_quality: dict[str, Any] = field(default_factory=dict)
    failure_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IndexComparisonRow:
    symbol: str
    market: str
    score: int
    action: str
    confidence: str
    latest_price: float | None
    change_pct: float | None
    return_20: float | None
    return_60: float | None
    rank: int
    model_used: str | None = None
    success: bool = True


@dataclass(slots=True)
class IndexComparisonResult:
    index_symbol: str
    report_date: date
    rows: list[IndexComparisonRow]
