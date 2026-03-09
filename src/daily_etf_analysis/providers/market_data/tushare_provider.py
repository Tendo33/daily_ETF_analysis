from __future__ import annotations

from datetime import date, datetime, timedelta

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    EtfDailyBar,
    EtfRealtimeQuote,
    Market,
    split_symbol,
)
from daily_etf_analysis.providers.market_data.base import MarketDataProvider


class TushareProvider(MarketDataProvider):
    name = "tushare"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _to_ts_code(self, symbol: str) -> str:
        market, code = split_symbol(symbol)
        if market != Market.CN:
            raise ValueError(f"Tushare only supports CN market: {symbol}")
        suffix = "SH" if code.startswith(("5", "6")) else "SZ"
        return f"{code}.{suffix}"

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        if not self.settings.tushare_token:
            return []

        import tushare as ts

        market, _ = split_symbol(symbol)
        if market != Market.CN:
            return []

        ts_code = self._to_ts_code(symbol)
        pro = ts.pro_api(self.settings.tushare_token)
        end = date.today()
        start = end - timedelta(days=days * 3)
        df = pro.fund_daily(
            ts_code=ts_code,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return []

        df = df.sort_values("trade_date").tail(days)
        bars: list[EtfDailyBar] = []
        for _, row in df.iterrows():
            trade_date = datetime.strptime(str(row["trade_date"]), "%Y%m%d").date()
            bars.append(
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=float(row.get("vol", 0))
                    if row.get("vol") is not None
                    else None,
                    amount=float(row.get("amount", 0))
                    if row.get("amount") is not None
                    else None,
                    pct_chg=float(row.get("pct_chg", 0))
                    if row.get("pct_chg") is not None
                    else None,
                    source=self.name,
                )
            )
        return bars

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        return None
