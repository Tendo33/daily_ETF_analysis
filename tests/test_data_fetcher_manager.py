from __future__ import annotations

from datetime import date, datetime

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import EtfDailyBar, EtfRealtimeQuote
from daily_etf_analysis.providers.market_data.base import (
    DataFetcherManager,
    MarketDataProvider,
)


class _FailProvider(MarketDataProvider):
    name = "fail"

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        raise RuntimeError("boom")

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        raise RuntimeError("boom")


class _SuccessProvider(MarketDataProvider):
    name = "success"

    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        return [
            EtfDailyBar(
                symbol=symbol,
                trade_date=date.today(),
                open=1,
                high=2,
                low=1,
                close=2,
                source=self.name,
            )
        ]

    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        return EtfRealtimeQuote(
            symbol=symbol,
            price=2.0,
            change_pct=1.0,
            quote_time=datetime.utcnow(),
            source=self.name,
        )


def test_failover_for_daily_and_realtime() -> None:
    settings = Settings()
    manager = DataFetcherManager(
        settings=settings, providers=[_FailProvider(), _SuccessProvider()]
    )
    bars, source = manager.get_daily_bars("CN:159659", days=5)
    quote, quote_source = manager.get_realtime_quote("CN:159659")

    assert len(bars) == 1
    assert source == "success"
    assert quote is not None
    assert quote_source == "success"
