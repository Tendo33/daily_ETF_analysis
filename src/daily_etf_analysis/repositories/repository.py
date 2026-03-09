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
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from daily_etf_analysis.config.settings import Settings, get_settings
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
                        updated_at=datetime.utcnow(),
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
            row.updated_at = datetime.utcnow()

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
                )
            )

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
