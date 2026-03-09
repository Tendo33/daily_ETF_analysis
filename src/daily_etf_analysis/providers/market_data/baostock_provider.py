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


class BaostockProvider(MarketDataProvider):
    name = "baostock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _to_bs_code(self, symbol: str) -> str:
        market, code = split_symbol(symbol)
        if market != Market.CN:
            raise ValueError(f"Baostock only supports CN market: {symbol}")
        if code.startswith(("5", "6", "9")):
            return f"sh.{code}"
        return f"sz.{code}"

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        import baostock as bs

        market, _ = split_symbol(symbol)
        if market != Market.CN:
            return []

        bs_code = self._to_bs_code(symbol)
        login_res = bs.login()
        if login_res.error_code != "0":
            return []
        try:
            end = date.today()
            start = end - timedelta(days=days * 3)
            rs = bs.query_history_k_data_plus(
                bs_code,
                fields="date,open,high,low,close,volume,amount,pctChg",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != "0":
                return []
            rows: list[dict[str, str]] = []
            while rs.next():
                rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=False)))
            if not rows:
                return []
            rows = rows[-days:]
            bars: list[EtfDailyBar] = []
            for row in rows:
                bars.append(
                    EtfDailyBar(
                        symbol=symbol,
                        trade_date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                        open=float(row.get("open") or 0),
                        high=float(row.get("high") or 0),
                        low=float(row.get("low") or 0),
                        close=float(row.get("close") or 0),
                        volume=float(row.get("volume") or 0),
                        amount=float(row.get("amount") or 0),
                        pct_chg=float(row.get("pctChg") or 0),
                        source=self.name,
                    )
                )
            return bars
        finally:
            bs.logout()

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        return None
