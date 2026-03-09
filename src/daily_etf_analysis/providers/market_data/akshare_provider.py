from __future__ import annotations

from datetime import datetime

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    EtfDailyBar,
    EtfRealtimeQuote,
    Market,
    split_symbol,
)
from daily_etf_analysis.providers.market_data.base import MarketDataProvider


class AkshareProvider(MarketDataProvider):
    name = "akshare"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        import akshare as ak

        market, code = split_symbol(symbol)
        if market == Market.CN:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
        elif market == Market.HK:
            df = ak.stock_hk_hist(symbol=code, period="daily", adjust="qfq")
        else:
            return []
        if df is None or df.empty:
            return []
        df = df.tail(days)

        bars: list[EtfDailyBar] = []
        for _, row in df.iterrows():
            bars.append(
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=row["日期"].date()
                    if hasattr(row["日期"], "date")
                    else datetime.strptime(str(row["日期"]), "%Y-%m-%d").date(),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
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
        import akshare as ak

        market, code = split_symbol(symbol)
        if market == Market.CN:
            df = ak.fund_etf_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"].astype(str) == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return EtfRealtimeQuote(
                symbol=symbol,
                price=float(r["最新价"]),
                change_pct=float(r.get("涨跌幅", 0)),
                turnover=float(r.get("换手率", 0))
                if r.get("换手率") is not None
                else None,
                amount=float(r.get("成交额", 0))
                if r.get("成交额") is not None
                else None,
                quote_time=datetime.utcnow(),
                source=self.name,
            )
        if market == Market.HK:
            df = ak.stock_hk_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"].astype(str).str.zfill(5) == code.zfill(5)]
            if row.empty:
                return None
            r = row.iloc[0]
            return EtfRealtimeQuote(
                symbol=symbol,
                price=float(r["最新价"]),
                change_pct=float(r.get("涨跌幅", 0)),
                amount=float(r.get("成交额", 0))
                if r.get("成交额") is not None
                else None,
                quote_time=datetime.utcnow(),
                source=self.name,
            )
        return None
