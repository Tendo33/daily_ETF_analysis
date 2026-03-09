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

_US_INDEX_TO_YF = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "IXIC": "^IXIC",
    "DJI": "^DJI",
    "VIX": "^VIX",
}


class YfinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _to_yf_symbol(self, symbol: str) -> str:
        market, code = split_symbol(symbol)
        if market == Market.US:
            return code
        if market == Market.INDEX:
            return _US_INDEX_TO_YF.get(code, code)
        if market == Market.CN:
            if code.startswith(("6", "5")):
                return f"{code}.SS"
            return f"{code}.SZ"
        if market == Market.HK:
            return f"{code.zfill(4)}.HK"
        raise ValueError(f"Unsupported market for yfinance symbol conversion: {symbol}")

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        import yfinance as yf

        yf_symbol = self._to_yf_symbol(symbol)
        end = date.today()
        start = end - timedelta(days=days * 2)
        df = yf.download(
            tickers=yf_symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
            timeout=self.settings.llm_timeout_seconds,
        )
        if df.empty:
            return []
        if "Close" not in df.columns:
            # Sometimes yfinance returns MultiIndex columns.
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        bars: list[EtfDailyBar] = []
        for index, row in df.tail(days).iterrows():
            close = float(row.get("Close", 0))
            open_ = float(row.get("Open", close))
            high = float(row.get("High", close))
            low = float(row.get("Low", close))
            volume = (
                float(row.get("Volume", 0)) if row.get("Volume") is not None else None
            )
            amount = volume * close if volume is not None else None
            bars.append(
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=index.date(),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    amount=amount,
                    source=self.name,
                )
            )
        return bars

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        import yfinance as yf

        yf_symbol = self._to_yf_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        previous = hist.iloc[-2] if len(hist) > 1 else latest
        price = float(latest["Close"])
        prev_close = float(previous["Close"])
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None
        volume = float(latest.get("Volume", 0))
        return EtfRealtimeQuote(
            symbol=symbol,
            price=price,
            change_pct=change_pct,
            volume=volume,
            amount=volume * price if volume else None,
            quote_time=datetime.utcnow(),
            source=self.name,
        )
