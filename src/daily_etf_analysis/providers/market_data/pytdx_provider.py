from __future__ import annotations

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


class PytdxProvider(MarketDataProvider):
    name = "pytdx"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _market_id(self, code: str) -> int:
        return 1 if code.startswith(("5", "6", "9")) else 0

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        from pytdx.hq import TdxHq_API
        from pytdx.params import TDXParams

        market, code = split_symbol(symbol)
        if market != Market.CN:
            return []

        api = TdxHq_API()
        connected = api.connect(self.settings.pytdx_host, int(self.settings.pytdx_port))
        if not connected:
            return []
        try:
            market_id = self._market_id(code)
            raw = api.get_security_bars(
                TDXParams.KLINE_TYPE_DAILY,
                market_id,
                code,
                0,
                max(days, 10),
            )
            if not raw:
                return []
            df = api.to_df(raw)
            if df is None or df.empty:
                return []
            df = df.sort_values("datetime").tail(days)
            bars: list[EtfDailyBar] = []
            for _, row in df.iterrows():
                trade_date = datetime.strptime(
                    str(row["datetime"])[:10], "%Y-%m-%d"
                ).date()
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
                        source=self.name,
                    )
                )
            return bars
        finally:
            api.disconnect()

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        from pytdx.hq import TdxHq_API

        market, code = split_symbol(symbol)
        if market != Market.CN:
            return None
        api = TdxHq_API()
        connected = api.connect(self.settings.pytdx_host, int(self.settings.pytdx_port))
        if not connected:
            return None
        try:
            market_id = self._market_id(code)
            raw = api.get_security_quotes([(market_id, code)])
            if not raw:
                return None
            quote = raw[0]
            price = float(quote.get("price", 0))
            last_close = float(quote.get("last_close", 0))
            change_pct = (
                ((price - last_close) / last_close * 100) if last_close else None
            )
            return EtfRealtimeQuote(
                symbol=symbol,
                price=price,
                change_pct=change_pct,
                volume=float(quote.get("vol", 0))
                if quote.get("vol") is not None
                else None,
                amount=float(quote.get("amount", 0))
                if quote.get("amount") is not None
                else None,
                quote_time=utc_now_naive(),
                source=self.name,
            )
        finally:
            api.disconnect()
