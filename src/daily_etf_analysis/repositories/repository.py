from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    desc,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    AnalysisTask,
    EtfAnalysisResult,
    EtfDailyBar,
    EtfInstrument,
    EtfRealtimeQuote,
    Market,
    TaskStatus,
)


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
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive)


class EtfAnalysisReportORM(Base):
    __tablename__ = "etf_analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
    factors_json: Mapped[str] = mapped_column(Text, default="{}")
    key_points_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_alerts_json: Mapped[str] = mapped_column(Text, default="[]")
    context_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    news_items_json: Mapped[str] = mapped_column(Text, default="[]")
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


class EtfRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_engine(self.settings.database_url, future=True)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False
        )
        self.init_db()

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Any:
        db: Session = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def replace_instruments(self, instruments: list[EtfInstrument]) -> None:
        with self.session() as db:
            db.query(EtfInstrumentORM).delete()
            for item in instruments:
                db.add(
                    EtfInstrumentORM(
                        symbol=item.symbol,
                        market=item.market.value,
                        code=item.code,
                        name=item.name,
                        benchmark_index=item.benchmark_index,
                        currency=item.currency,
                        enabled=item.enabled,
                        updated_at=utc_now_naive(),
                    )
                )

    def list_instruments(self) -> list[EtfInstrument]:
        with self.session() as db:
            rows = (
                db.execute(select(EtfInstrumentORM).order_by(EtfInstrumentORM.symbol))
                .scalars()
                .all()
            )
            return [
                EtfInstrument(
                    symbol=row.symbol,
                    market=Market(row.market),
                    code=row.code,
                    name=row.name,
                    benchmark_index=row.benchmark_index,
                    currency=row.currency,
                    enabled=row.enabled,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def replace_index_mappings(self, mapping: dict[str, list[str]]) -> None:
        with self.session() as db:
            db.query(IndexProxyMappingORM).delete()
            for index_symbol, proxies in mapping.items():
                for priority, proxy in enumerate(proxies):
                    db.add(
                        IndexProxyMappingORM(
                            index_symbol=index_symbol,
                            proxy_symbol=proxy,
                            priority=priority,
                        )
                    )

    def list_index_mappings(self) -> dict[str, list[str]]:
        with self.session() as db:
            rows = db.execute(
                select(IndexProxyMappingORM).order_by(
                    IndexProxyMappingORM.index_symbol, IndexProxyMappingORM.priority
                )
            ).scalars()
            mapping: dict[str, list[str]] = {}
            for row in rows:
                mapping.setdefault(row.index_symbol, []).append(row.proxy_symbol)
            return mapping

    def get_index_proxy_symbols(self, index_symbol: str) -> list[str]:
        mapping = self.list_index_mappings()
        return mapping.get(index_symbol.upper(), [])

    def save_daily_bars(self, bars: list[EtfDailyBar]) -> None:
        if not bars:
            return
        with self.session() as db:
            for bar in bars:
                existing = db.execute(
                    select(EtfDailyBarORM).where(
                        EtfDailyBarORM.symbol == bar.symbol,
                        EtfDailyBarORM.trade_date == bar.trade_date,
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.open = bar.open
                    existing.high = bar.high
                    existing.low = bar.low
                    existing.close = bar.close
                    existing.volume = bar.volume
                    existing.amount = bar.amount
                    existing.pct_chg = bar.pct_chg
                    existing.source = bar.source
                else:
                    db.add(
                        EtfDailyBarORM(
                            symbol=bar.symbol,
                            trade_date=bar.trade_date,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=bar.volume,
                            amount=bar.amount,
                            pct_chg=bar.pct_chg,
                            source=bar.source,
                        )
                    )

    def get_recent_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        cutoff = date.today() - timedelta(days=days * 2)
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfDailyBarORM)
                    .where(
                        EtfDailyBarORM.symbol == symbol,
                        EtfDailyBarORM.trade_date >= cutoff,
                    )
                    .order_by(EtfDailyBarORM.trade_date)
                )
                .scalars()
                .all()
            )
            return [
                EtfDailyBar(
                    symbol=row.symbol,
                    trade_date=row.trade_date,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    amount=row.amount,
                    pct_chg=row.pct_chg,
                    source=row.source,
                )
                for row in rows
            ]

    def save_realtime_quote(self, quote: EtfRealtimeQuote) -> None:
        with self.session() as db:
            db.add(
                EtfRealtimeQuoteORM(
                    symbol=quote.symbol,
                    quote_time=quote.quote_time,
                    price=quote.price,
                    change_pct=quote.change_pct,
                    turnover=quote.turnover,
                    volume=quote.volume,
                    amount=quote.amount,
                    source=quote.source,
                )
            )

    def get_latest_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        with self.session() as db:
            row = (
                db.execute(
                    select(EtfRealtimeQuoteORM)
                    .where(EtfRealtimeQuoteORM.symbol == symbol)
                    .order_by(desc(EtfRealtimeQuoteORM.quote_time))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return EtfRealtimeQuote(
                symbol=row.symbol,
                price=row.price,
                change_pct=row.change_pct,
                turnover=row.turnover,
                volume=row.volume,
                amount=row.amount,
                quote_time=row.quote_time,
                source=row.source,
            )

    def create_task(self, task: AnalysisTask) -> None:
        with self.session() as db:
            db.add(
                AnalysisTaskORM(
                    task_id=task.task_id,
                    status=task.status.value,
                    symbols_json=json.dumps(task.symbols, ensure_ascii=False),
                    force_refresh=task.force_refresh,
                    error=task.error,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
            )

    def update_task(
        self, task_id: str, status: TaskStatus, error: str | None = None
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id)
            ).scalar_one()
            row.status = status.value
            row.error = error
            row.updated_at = utc_now_naive()

    def get_task(self, task_id: str) -> AnalysisTask | None:
        with self.session() as db:
            row = db.execute(
                select(AnalysisTaskORM).where(AnalysisTaskORM.task_id == task_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return AnalysisTask(
                task_id=row.task_id,
                status=TaskStatus(row.status),
                symbols=json.loads(row.symbols_json),
                force_refresh=row.force_refresh,
                created_at=row.created_at,
                updated_at=row.updated_at,
                error=row.error,
            )

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(AnalysisTaskORM)
                    .order_by(desc(AnalysisTaskORM.updated_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                AnalysisTask(
                    task_id=row.task_id,
                    status=TaskStatus(row.status),
                    symbols=json.loads(row.symbols_json),
                    force_refresh=row.force_refresh,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    error=row.error,
                )
                for row in rows
            ]

    def save_analysis_report(
        self,
        task_id: str,
        symbol: str,
        trade_date: date,
        factors: dict[str, Any],
        result: EtfAnalysisResult,
        context_snapshot: dict[str, Any] | None = None,
        news_items: list[dict[str, Any]] | None = None,
    ) -> None:
        with self.session() as db:
            db.add(
                EtfAnalysisReportORM(
                    task_id=task_id,
                    symbol=symbol,
                    trade_date=trade_date,
                    score=result.score,
                    trend=result.trend.value,
                    action=result.action.value,
                    confidence=result.confidence.value,
                    summary=result.summary,
                    model_used=result.model_used,
                    success=result.success,
                    error_message=result.error_message,
                    factors_json=json.dumps(factors, ensure_ascii=False),
                    key_points_json=json.dumps(result.key_points, ensure_ascii=False),
                    risk_alerts_json=json.dumps(result.risk_alerts, ensure_ascii=False),
                    context_snapshot_json=json.dumps(
                        context_snapshot or {}, ensure_ascii=False
                    ),
                    news_items_json=json.dumps(news_items or [], ensure_ascii=False),
                    created_at=utc_now_naive(),
                )
            )

    def list_history(
        self, page: int = 1, limit: int = 20, symbol: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        offset = max(0, (page - 1) * limit)
        with self.session() as db:
            query = select(EtfAnalysisReportORM)
            count_query = select(func.count()).select_from(EtfAnalysisReportORM)
            if symbol:
                normalized = symbol.upper()
                query = query.where(EtfAnalysisReportORM.symbol == normalized)
                count_query = count_query.where(
                    EtfAnalysisReportORM.symbol == normalized
                )
            total = int(db.execute(count_query).scalar() or 0)
            rows = (
                db.execute(
                    query.order_by(
                        desc(EtfAnalysisReportORM.trade_date),
                        desc(EtfAnalysisReportORM.id),
                    )
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            items = [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "symbol": row.symbol,
                    "trade_date": row.trade_date.isoformat(),
                    "score": row.score,
                    "action": row.action,
                    "confidence": row.confidence,
                    "summary": row.summary,
                    "success": row.success,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
            return items, total

    def get_history_record(self, record_id: int) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                select(EtfAnalysisReportORM).where(EtfAnalysisReportORM.id == record_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "task_id": row.task_id,
                "symbol": row.symbol,
                "trade_date": row.trade_date.isoformat(),
                "score": row.score,
                "trend": row.trend,
                "action": row.action,
                "confidence": row.confidence,
                "summary": row.summary,
                "model_used": row.model_used,
                "success": row.success,
                "error_message": row.error_message,
                "factors": json.loads(row.factors_json),
                "key_points": json.loads(row.key_points_json),
                "risk_alerts": json.loads(row.risk_alerts_json),
                "context_snapshot": json.loads(row.context_snapshot_json),
                "news_items": json.loads(row.news_items_json),
                "created_at": row.created_at.isoformat(),
            }

    def get_history_news(self, record_id: int) -> list[dict[str, Any]]:
        record = self.get_history_record(record_id)
        if not record:
            return []
        value = record.get("news_items", [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def create_backtest_run(
        self, eval_window_days: int, symbols: list[str], disclaimer: str
    ) -> str:
        run_id = utc_now_naive().strftime("%Y%m%d%H%M%S%f")
        with self.session() as db:
            db.add(
                BacktestRunORM(
                    run_id=run_id,
                    eval_window_days=eval_window_days,
                    symbols_json=json.dumps([s.upper() for s in symbols]),
                    disclaimer=disclaimer,
                )
            )
        return run_id

    def update_backtest_run_summary(
        self,
        run_id: str,
        total_samples: int,
        evaluated_samples: int,
        skipped_count: int,
        direction_hit_rate: float | None,
        avg_return: float | None,
        max_drawdown: float | None,
        win_rate: float | None,
    ) -> None:
        with self.session() as db:
            row = db.execute(
                select(BacktestRunORM).where(BacktestRunORM.run_id == run_id)
            ).scalar_one()
            row.total_samples = total_samples
            row.evaluated_samples = evaluated_samples
            row.skipped_count = skipped_count
            row.direction_hit_rate = direction_hit_rate
            row.avg_return = avg_return
            row.max_drawdown = max_drawdown
            row.win_rate = win_rate

    def save_backtest_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        with self.session() as db:
            db.query(BacktestResultORM).filter(
                BacktestResultORM.run_id == run_id
            ).delete()
            for item in results:
                db.add(
                    BacktestResultORM(
                        run_id=run_id,
                        symbol=str(item.get("symbol", "")).upper(),
                        trade_date=item.get("trade_date"),
                        sample_count=int(item.get("sample_count", 0)),
                        evaluated_count=int(item.get("evaluated_count", 0)),
                        skipped_count=int(item.get("skipped_count", 0)),
                        direction_hit_rate=_float_or_none(
                            item.get("direction_hit_rate")
                        ),
                        avg_return=_float_or_none(item.get("avg_return")),
                        max_drawdown=_float_or_none(item.get("max_drawdown")),
                        win_rate=_float_or_none(item.get("win_rate")),
                        details_json=json.dumps(
                            item.get("details", {}), ensure_ascii=False
                        ),
                    )
                )

    def get_backtest_run(self, run_id: str) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                select(BacktestRunORM).where(BacktestRunORM.run_id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "run_id": row.run_id,
                "eval_window_days": row.eval_window_days,
                "symbols": json.loads(row.symbols_json),
                "total_samples": row.total_samples,
                "evaluated_samples": row.evaluated_samples,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
                "disclaimer": row.disclaimer,
                "created_at": row.created_at.isoformat(),
            }

    def get_latest_backtest_run(self) -> dict[str, Any] | None:
        with self.session() as db:
            row = (
                db.execute(
                    select(BacktestRunORM).order_by(desc(BacktestRunORM.created_at))
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "run_id": row.run_id,
                "eval_window_days": row.eval_window_days,
                "symbols": json.loads(row.symbols_json),
                "total_samples": row.total_samples,
                "evaluated_samples": row.evaluated_samples,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
                "disclaimer": row.disclaimer,
                "created_at": row.created_at.isoformat(),
            }

    def get_backtest_results(self, run_id: str) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = (
                db.execute(
                    select(BacktestResultORM)
                    .where(BacktestResultORM.run_id == run_id)
                    .order_by(BacktestResultORM.symbol)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "symbol": row.symbol,
                    "trade_date": row.trade_date.isoformat()
                    if row.trade_date is not None
                    else None,
                    "sample_count": row.sample_count,
                    "evaluated_count": row.evaluated_count,
                    "skipped_count": row.skipped_count,
                    "direction_hit_rate": row.direction_hit_rate,
                    "avg_return": row.avg_return,
                    "max_drawdown": row.max_drawdown,
                    "win_rate": row.win_rate,
                    "details": json.loads(row.details_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def get_backtest_symbol_performance(
        self, run_id: str, symbol: str
    ) -> dict[str, Any] | None:
        normalized = symbol.upper()
        with self.session() as db:
            row = (
                db.execute(
                    select(BacktestResultORM)
                    .where(
                        BacktestResultORM.run_id == run_id,
                        BacktestResultORM.symbol == normalized,
                    )
                    .order_by(desc(BacktestResultORM.created_at))
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "symbol": row.symbol,
                "sample_count": row.sample_count,
                "evaluated_count": row.evaluated_count,
                "skipped_count": row.skipped_count,
                "direction_hit_rate": row.direction_hit_rate,
                "avg_return": row.avg_return,
                "max_drawdown": row.max_drawdown,
                "win_rate": row.win_rate,
            }

    def create_system_config_snapshot(
        self, config_payload: dict[str, Any], actor: str, expected_version: int | None
    ) -> int:
        with self.session() as db:
            latest_version = (
                db.execute(select(func.max(SystemConfigSnapshotORM.version))).scalar()
                or 0
            )
            if expected_version is not None and expected_version != int(latest_version):
                raise ValueError(
                    f"version_conflict: expected={expected_version}, actual={latest_version}"
                )
            new_version = int(latest_version) + 1
            db.add(
                SystemConfigSnapshotORM(
                    version=new_version,
                    config_json=json.dumps(config_payload, ensure_ascii=False),
                    created_by=actor,
                )
            )
            return new_version

    def get_latest_system_config_snapshot(self) -> dict[str, Any] | None:
        with self.session() as db:
            row = (
                db.execute(
                    select(SystemConfigSnapshotORM).order_by(
                        desc(SystemConfigSnapshotORM.version)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "version": row.version,
                "config": json.loads(row.config_json),
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat(),
            }

    def create_system_config_audit_log(
        self, version: int, actor: str, action: str, changes: dict[str, Any]
    ) -> None:
        with self.session() as db:
            db.add(
                SystemConfigAuditLogORM(
                    version=version,
                    actor=actor,
                    action=action,
                    changes_json=json.dumps(changes, ensure_ascii=False),
                )
            )

    def list_system_config_audit_logs(
        self, page: int = 1, limit: int = 20
    ) -> list[dict[str, Any]]:
        offset = max(0, (page - 1) * limit)
        with self.session() as db:
            rows = (
                db.execute(
                    select(SystemConfigAuditLogORM)
                    .order_by(desc(SystemConfigAuditLogORM.id))
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "version": row.version,
                    "actor": row.actor,
                    "action": row.action,
                    "changes": json.loads(row.changes_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def delete_system_config_snapshot(self, version: int) -> None:
        with self.session() as db:
            db.query(SystemConfigSnapshotORM).filter(
                SystemConfigSnapshotORM.version == version
            ).delete()

    def get_backtest_signals(self, symbols: list[str]) -> list[dict[str, Any]]:
        normalized_symbols = [s.upper() for s in symbols]
        if not normalized_symbols:
            return []
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfAnalysisReportORM)
                    .where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                    .order_by(
                        EtfAnalysisReportORM.symbol,
                        EtfAnalysisReportORM.trade_date,
                        EtfAnalysisReportORM.id,
                    )
                )
                .scalars()
                .all()
            )
            return [
                {
                    "symbol": row.symbol,
                    "trade_date": row.trade_date,
                    "action": row.action,
                }
                for row in rows
            ]

    def get_price_series(self, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
        normalized_symbols = [s.upper() for s in symbols]
        if not normalized_symbols:
            return {}
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfDailyBarORM)
                    .where(EtfDailyBarORM.symbol.in_(normalized_symbols))
                    .order_by(EtfDailyBarORM.symbol, EtfDailyBarORM.trade_date)
                )
                .scalars()
                .all()
            )
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row.symbol, []).append(
                    {"trade_date": row.trade_date, "close": row.close}
                )
            return grouped

    def get_daily_reports(
        self, report_date: date, market: str | None = None
    ) -> list[dict[str, Any]]:
        with self.session() as db:
            query = select(EtfAnalysisReportORM).where(
                EtfAnalysisReportORM.trade_date == report_date
            )
            rows = (
                db.execute(query.order_by(EtfAnalysisReportORM.symbol)).scalars().all()
            )
            result = []
            for row in rows:
                if market and not row.symbol.startswith(market.upper() + ":"):
                    continue
                result.append(
                    {
                        "task_id": row.task_id,
                        "symbol": row.symbol,
                        "trade_date": row.trade_date.isoformat(),
                        "score": row.score,
                        "trend": row.trend,
                        "action": row.action,
                        "confidence": row.confidence,
                        "summary": row.summary,
                        "model_used": row.model_used,
                        "success": row.success,
                        "error_message": row.error_message,
                        "factors": json.loads(row.factors_json),
                        "key_points": json.loads(row.key_points_json),
                        "risk_alerts": json.loads(row.risk_alerts_json),
                    }
                )
            return result

    def get_recent_signals(
        self, symbols: list[str], limit: int
    ) -> dict[str, list[dict[str, Any]]]:
        if not symbols or limit <= 0:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfAnalysisReportORM)
                    .where(EtfAnalysisReportORM.symbol.in_(normalized_symbols))
                    .order_by(
                        EtfAnalysisReportORM.symbol,
                        desc(EtfAnalysisReportORM.trade_date),
                        desc(EtfAnalysisReportORM.id),
                    )
                )
                .scalars()
                .all()
            )
            results: dict[str, list[dict[str, Any]]] = {
                s: [] for s in normalized_symbols
            }
            for row in rows:
                bucket = results.setdefault(row.symbol, [])
                if len(bucket) >= limit:
                    continue
                bucket.append(
                    {
                        "trade_date": row.trade_date.isoformat(),
                        "action": row.action,
                        "trend": row.trend,
                        "score": row.score,
                    }
                )
            return {k: v for k, v in results.items() if v}

    def get_latest_report_trade_date_for_task(self, task_id: str) -> date | None:
        with self.session() as db:
            return (
                db.execute(
                    select(EtfAnalysisReportORM.trade_date)
                    .where(EtfAnalysisReportORM.task_id == task_id)
                    .order_by(desc(EtfAnalysisReportORM.trade_date))
                    .limit(1)
                )
                .scalars()
                .first()
            )

    def get_latest_reports_for_symbols(
        self, symbols: list[str], report_date: date | None = None
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            query = select(EtfAnalysisReportORM).where(
                EtfAnalysisReportORM.symbol.in_(normalized_symbols)
            )
            if report_date is not None:
                query = query.where(EtfAnalysisReportORM.trade_date == report_date)
            rows = (
                db.execute(
                    query.order_by(
                        EtfAnalysisReportORM.symbol,
                        desc(EtfAnalysisReportORM.trade_date),
                    )
                )
                .scalars()
                .all()
            )
            latest: dict[str, dict[str, Any]] = {}
            for row in rows:
                if row.symbol in latest:
                    continue
                latest[row.symbol] = {
                    "symbol": row.symbol,
                    "trade_date": row.trade_date,
                    "score": row.score,
                    "trend": row.trend,
                    "action": row.action,
                    "confidence": row.confidence,
                    "summary": row.summary,
                    "model_used": row.model_used,
                    "success": row.success,
                    "error_message": row.error_message,
                    "factors": json.loads(row.factors_json),
                    "key_points": json.loads(row.key_points_json),
                    "risk_alerts": json.loads(row.risk_alerts_json),
                }
            return latest

    def get_latest_quotes_for_symbols(
        self, symbols: list[str]
    ) -> dict[str, EtfRealtimeQuote]:
        if not symbols:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            rows = (
                db.execute(
                    select(EtfRealtimeQuoteORM)
                    .where(EtfRealtimeQuoteORM.symbol.in_(normalized_symbols))
                    .order_by(
                        EtfRealtimeQuoteORM.symbol, desc(EtfRealtimeQuoteORM.quote_time)
                    )
                )
                .scalars()
                .all()
            )
            latest: dict[str, EtfRealtimeQuote] = {}
            for row in rows:
                if row.symbol in latest:
                    continue
                latest[row.symbol] = EtfRealtimeQuote(
                    symbol=row.symbol,
                    price=row.price,
                    change_pct=row.change_pct,
                    turnover=row.turnover,
                    volume=row.volume,
                    amount=row.amount,
                    quote_time=row.quote_time,
                    source=row.source,
                )
            return latest

    def count_expired_records(
        self,
        *,
        task_created_before: datetime,
        report_created_before: datetime,
        quote_time_before: datetime,
    ) -> dict[str, int]:
        with self.session() as db:
            task_count = int(
                db.execute(
                    select(func.count())
                    .select_from(AnalysisTaskORM)
                    .where(AnalysisTaskORM.created_at < task_created_before)
                ).scalar()
                or 0
            )
            report_count = int(
                db.execute(
                    select(func.count())
                    .select_from(EtfAnalysisReportORM)
                    .where(EtfAnalysisReportORM.created_at < report_created_before)
                ).scalar()
                or 0
            )
            quote_count = int(
                db.execute(
                    select(func.count())
                    .select_from(EtfRealtimeQuoteORM)
                    .where(EtfRealtimeQuoteORM.quote_time < quote_time_before)
                ).scalar()
                or 0
            )
            return {
                "tasks": task_count,
                "reports": report_count,
                "quotes": quote_count,
            }

    def delete_expired_records(
        self,
        *,
        task_created_before: datetime,
        report_created_before: datetime,
        quote_time_before: datetime,
    ) -> dict[str, int]:
        with self.session() as db:
            deleted_tasks = (
                db.query(AnalysisTaskORM)
                .filter(AnalysisTaskORM.created_at < task_created_before)
                .delete()
            )
            deleted_reports = (
                db.query(EtfAnalysisReportORM)
                .filter(EtfAnalysisReportORM.created_at < report_created_before)
                .delete()
            )
            deleted_quotes = (
                db.query(EtfRealtimeQuoteORM)
                .filter(EtfRealtimeQuoteORM.quote_time < quote_time_before)
                .delete()
            )
            return {
                "tasks": int(deleted_tasks),
                "reports": int(deleted_reports),
                "quotes": int(deleted_quotes),
            }


def _float_or_none(value: object) -> float | None:
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
