from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import TaskErrorCode


class Base(DeclarativeBase):
    pass


class EtfInstrumentORM(Base):
    __tablename__ = "etf_instruments"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    market: Mapped[str] = mapped_column(String(12), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    benchmark_index: Mapped[str] = mapped_column(String(32), default="")
    currency: Mapped[str] = mapped_column(String(16), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class IndexProxyMappingORM(Base):
    __tablename__ = "index_proxy_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    proxy_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class EtfDailyBarORM(Base):
    __tablename__ = "etf_daily_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_etf_daily_symbol_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_chg: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="")


class EtfRealtimeQuoteORM(Base):
    __tablename__ = "etf_realtime_quotes"
    __table_args__ = (
        Index(
            "ix_etf_realtime_quotes_symbol_quote_time",
            "symbol",
            "quote_time",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quote_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="")


class AnalysisTaskORM(Base):
    __tablename__ = "analysis_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    force_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str] = mapped_column(
        String(64), default=TaskErrorCode.NONE.value
    )
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    skipped_symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class EtfAnalysisReportORM(Base):
    __tablename__ = "etf_analysis_reports"
    __table_args__ = (
        Index(
            "ix_etf_analysis_reports_symbol_trade_date_id",
            "symbol",
            "trade_date",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    trend: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    horizon: Mapped[str] = mapped_column(
        String(32), nullable=False, default="next_trading_day"
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    factors_json: Mapped[str] = mapped_column(Text, default="{}")
    key_points_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_alerts_json: Mapped[str] = mapped_column(Text, default="[]")
    context_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    news_items_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class AnalysisRunORM(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    market: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    run_window: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_tasks: Mapped[int] = mapped_column(Integer, default=0)
    decision_quality_json: Mapped[str] = mapped_column(Text, default="{}")
    failure_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnalysisRunAuditLogORM(Base):
    __tablename__ = "analysis_run_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class BacktestRunORM(Base):
    __tablename__ = "backtest_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    eval_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    symbols_json: Mapped[str] = mapped_column(Text, default="[]")
    total_samples: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_samples: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    direction_hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    disclaimer: Mapped[str] = mapped_column(
        Text, default="For research only; not investment advice."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class BacktestResultORM(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    direction_hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class SystemConfigSnapshotORM(Base):
    __tablename__ = "system_config_snapshots"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="system"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class SystemConfigAuditLogORM(Base):
    __tablename__ = "system_config_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="update")
    changes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
