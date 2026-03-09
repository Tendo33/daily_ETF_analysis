from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from daily_etf_analysis.domain.enums import (
    Action,
    Confidence,
    Market,
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
    updated_at: datetime = field(default_factory=datetime.utcnow)


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
    quote_time: datetime = field(default_factory=datetime.utcnow)
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
    key_points: list[str] = field(default_factory=list)
    risk_alerts: list[str] = field(default_factory=list)
    model_used: str | None = None
    success: bool = True
    error_message: str | None = None
    raw_response: str | None = None

    @classmethod
    def neutral_fallback(cls, symbol: str, error_message: str) -> EtfAnalysisResult:
        return cls(
            symbol=symbol,
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
        )


@dataclass(slots=True)
class AnalysisTask:
    task_id: str
    status: TaskStatus
    symbols: list[str]
    force_refresh: bool
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


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
