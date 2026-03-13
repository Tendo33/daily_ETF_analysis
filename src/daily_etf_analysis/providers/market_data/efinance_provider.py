from __future__ import annotations

import logging
from datetime import datetime

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.domain import (
    EtfDailyBar,
    EtfRealtimeQuote,
    Market,
    split_symbol,
)
from daily_etf_analysis.providers.market_data.base import MarketDataProvider

logger = logging.getLogger(__name__)


class EfinanceProvider(MarketDataProvider):
    name = "efinance"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        import efinance as ef

        market, code = split_symbol(symbol)
        if market not in {Market.CN, Market.HK}:
            return []

        history = ef.stock.get_quote_history(code, klt=101)
        if history is None or history.empty:
            return []
        history = history.tail(days)

        bars: list[EtfDailyBar] = []
        for _, row in history.iterrows():
            date_obj = row.get("日期")
            if hasattr(date_obj, "date"):
                trade_date = date_obj.date()
            else:
                trade_date = datetime.strptime(str(date_obj), "%Y-%m-%d").date()
            bars.append(
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row.get("开盘", 0)),
                    high=float(row.get("最高", 0)),
                    low=float(row.get("最低", 0)),
                    close=float(row.get("收盘", 0)),
                    volume=float(row.get("成交量", 0))
                    if row.get("成交量") is not None
                    else None,
                    amount=float(row.get("成交额", 0))
                    if row.get("成交额") is not None
                    else None,
                    pct_chg=float(row.get("涨跌幅", 0))
                    if row.get("涨跌幅") is not None
                    else None,
                    source=self.name,
                )
            )
        return bars

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        import efinance as ef

        market, code = split_symbol(symbol)
        if market not in {Market.CN, Market.HK}:
            return None

        quotes = ef.stock.get_realtime_quotes()
        if quotes is None or quotes.empty:
            return None
        row = quotes[quotes["股票代码"].astype(str).str.upper() == code.upper()]
        if row.empty:
            return None
        r = row.iloc[0]
        return EtfRealtimeQuote(
            symbol=symbol,
            price=float(r.get("最新价", 0)),
            change_pct=float(r.get("涨跌幅", 0))
            if r.get("涨跌幅") is not None
            else None,
            turnover=float(r.get("换手率", 0)) if r.get("换手率") is not None else None,
            volume=float(r.get("成交量", 0)) if r.get("成交量") is not None else None,
            amount=float(r.get("成交额", 0)) if r.get("成交额") is not None else None,
            quote_time=utc_now_naive(),
            source=self.name,
        )
