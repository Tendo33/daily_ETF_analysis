from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    EtfDailyBar,
    EtfInstrument,
    EtfRealtimeQuote,
    Market,
)
from daily_etf_analysis.repositories.models import (
    EtfDailyBarORM,
    EtfInstrumentORM,
    EtfRealtimeQuoteORM,
    IndexProxyMappingORM,
)


class MarketDataRepositoryMixin:
    def session(self) -> Any:
        raise NotImplementedError

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
            values = [
                {
                    "symbol": bar.symbol,
                    "trade_date": bar.trade_date,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "amount": bar.amount,
                    "pct_chg": bar.pct_chg,
                    "source": bar.source,
                }
                for bar in bars
            ]
            stmt = sqlite_insert(EtfDailyBarORM).values(values)
            upsert = stmt.on_conflict_do_update(
                index_elements=["symbol", "trade_date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "amount": stmt.excluded.amount,
                    "pct_chg": stmt.excluded.pct_chg,
                    "source": stmt.excluded.source,
                },
            )
            db.execute(upsert)

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

    def get_latest_quotes_for_symbols(
        self, symbols: list[str]
    ) -> dict[str, EtfRealtimeQuote]:
        if not symbols:
            return {}
        normalized_symbols = [s.upper() for s in symbols]
        with self.session() as db:
            try:
                ranked = (
                    select(
                        EtfRealtimeQuoteORM.id.label("id"),
                        EtfRealtimeQuoteORM.symbol.label("symbol"),
                        func.row_number()
                        .over(
                            partition_by=EtfRealtimeQuoteORM.symbol,
                            order_by=(
                                desc(EtfRealtimeQuoteORM.quote_time),
                                desc(EtfRealtimeQuoteORM.id),
                            ),
                        )
                        .label("row_num"),
                    )
                    .where(EtfRealtimeQuoteORM.symbol.in_(normalized_symbols))
                    .subquery()
                )
                latest_ids = (
                    db.execute(select(ranked.c.id).where(ranked.c.row_num == 1))
                    .scalars()
                    .all()
                )
                if not latest_ids:
                    return {}
                rows = (
                    db.execute(
                        select(EtfRealtimeQuoteORM).where(
                            EtfRealtimeQuoteORM.id.in_(latest_ids)
                        )
                    )
                    .scalars()
                    .all()
                )
            except Exception:
                rows = (
                    db.execute(
                        select(EtfRealtimeQuoteORM)
                        .where(EtfRealtimeQuoteORM.symbol.in_(normalized_symbols))
                        .order_by(
                            EtfRealtimeQuoteORM.symbol,
                            desc(EtfRealtimeQuoteORM.quote_time),
                            desc(EtfRealtimeQuoteORM.id),
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
