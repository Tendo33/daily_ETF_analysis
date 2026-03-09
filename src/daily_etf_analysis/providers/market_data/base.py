from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.domain import (
    EtfDailyBar,
    EtfRealtimeQuote,
    Market,
    split_symbol,
)

logger = logging.getLogger(__name__)


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_daily_bars(self, symbol: str, days: int = 120) -> list[EtfDailyBar]:
        raise NotImplementedError

    @abstractmethod
    def get_realtime_quote(self, symbol: str) -> EtfRealtimeQuote | None:
        raise NotImplementedError


class DataFetcherManager:
    def __init__(
        self,
        settings: Settings | None = None,
        providers: Sequence[MarketDataProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if providers is not None:
            self.providers = list(providers)
        else:
            self.providers = self._build_default_providers()

    def _build_default_providers(self) -> list[MarketDataProvider]:
        from daily_etf_analysis.providers.market_data.akshare_provider import (
            AkshareProvider,
        )
        from daily_etf_analysis.providers.market_data.efinance_provider import (
            EfinanceProvider,
        )
        from daily_etf_analysis.providers.market_data.yfinance_provider import (
            YfinanceProvider,
        )

        provider_map = {
            "efinance": EfinanceProvider(self.settings),
            "akshare": AkshareProvider(self.settings),
            "yfinance": YfinanceProvider(self.settings),
        }
        ordered = [
            provider_map[name]
            for name in self.settings.realtime_source_priority
            if name in provider_map
        ]
        for _name, provider in provider_map.items():
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    def _ordered_for_symbol(self, symbol: str) -> list[MarketDataProvider]:
        market, _ = split_symbol(symbol)
        if market == Market.US:
            # US market is primarily served by yfinance.
            yfinance_first = sorted(
                self.providers, key=lambda p: 0 if p.name == "yfinance" else 1
            )
            return yfinance_first
        return list(self.providers)

    def get_daily_bars(
        self, symbol: str, days: int = 120
    ) -> tuple[list[EtfDailyBar], str]:
        errors: list[str] = []
        for provider in self._ordered_for_symbol(symbol):
            try:
                bars = provider.get_daily_bars(symbol=symbol, days=days)
                if bars:
                    return bars, provider.name
                errors.append(f"{provider.name}: empty result")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name}: {exc}")
                logger.warning(
                    "Daily bars fetch failed for %s via %s: %s",
                    symbol,
                    provider.name,
                    exc,
                )
        raise RuntimeError(
            f"All market providers failed for {symbol}: {'; '.join(errors)}"
        )

    def get_realtime_quote(
        self, symbol: str
    ) -> tuple[EtfRealtimeQuote | None, str | None]:
        errors: list[str] = []
        for provider in self._ordered_for_symbol(symbol):
            try:
                quote = provider.get_realtime_quote(symbol=symbol)
                if quote:
                    return quote, provider.name
                errors.append(f"{provider.name}: empty result")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name}: {exc}")
                logger.warning(
                    "Realtime quote fetch failed for %s via %s: %s",
                    symbol,
                    provider.name,
                    exc,
                )
        logger.warning(
            "All realtime providers failed for %s: %s", symbol, "; ".join(errors)
        )
        return None, None
