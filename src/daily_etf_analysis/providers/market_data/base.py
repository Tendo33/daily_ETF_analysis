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
from daily_etf_analysis.providers.resilience import CircuitBreaker, run_with_resilience

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
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        if providers is not None:
            self.providers = list(providers)
        else:
            self.providers = self._build_default_providers()

    def _build_default_providers(self) -> list[MarketDataProvider]:
        from daily_etf_analysis.providers.market_data.akshare_provider import (
            AkshareProvider,
        )
        from daily_etf_analysis.providers.market_data.baostock_provider import (
            BaostockProvider,
        )
        from daily_etf_analysis.providers.market_data.efinance_provider import (
            EfinanceProvider,
        )
        from daily_etf_analysis.providers.market_data.pytdx_provider import (
            PytdxProvider,
        )
        from daily_etf_analysis.providers.market_data.tushare_provider import (
            TushareProvider,
        )
        from daily_etf_analysis.providers.market_data.yfinance_provider import (
            YfinanceProvider,
        )

        provider_map = {
            "efinance": EfinanceProvider(self.settings),
            "akshare": AkshareProvider(self.settings),
            "tushare": TushareProvider(self.settings),
            "pytdx": PytdxProvider(self.settings),
            "baostock": BaostockProvider(self.settings),
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

            def _fetch_daily(
                current_provider: MarketDataProvider = provider,
            ) -> list[EtfDailyBar]:
                return current_provider.get_daily_bars(symbol=symbol, days=days)

            try:
                bars = run_with_resilience(
                    provider=provider.name,
                    operation="daily_bars",
                    call=_fetch_daily,
                    settings=self.settings,
                    circuit_breakers=self._circuit_breakers,
                )
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

            def _fetch_quote(
                current_provider: MarketDataProvider = provider,
            ) -> EtfRealtimeQuote | None:
                return current_provider.get_realtime_quote(symbol=symbol)

            try:
                quote = run_with_resilience(
                    provider=provider.name,
                    operation="realtime_quote",
                    call=_fetch_quote,
                    settings=self.settings,
                    circuit_breakers=self._circuit_breakers,
                )
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
