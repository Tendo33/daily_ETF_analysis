from __future__ import annotations

import logging
from datetime import date

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.trading_calendar import is_market_open_today
from daily_etf_analysis.domain import (
    EtfAnalysisContext,
    EtfAnalysisResult,
    EtfInstrument,
    normalize_symbol,
    split_symbol,
)
from daily_etf_analysis.llm import EtfAnalyzer
from daily_etf_analysis.providers.market_data import DataFetcherManager
from daily_etf_analysis.providers.news import NewsProviderManager
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.factor_engine import compute_factors

logger = logging.getLogger(__name__)


class DailyPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: EtfRepository | None = None,
        fetcher_manager: DataFetcherManager | None = None,
        news_manager: NewsProviderManager | None = None,
        analyzer: EtfAnalyzer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or EtfRepository(self.settings)
        self.fetcher_manager = fetcher_manager or DataFetcherManager(self.settings)
        self.news_manager = news_manager or NewsProviderManager(self.settings)
        self.analyzer = analyzer or EtfAnalyzer(self.settings)
        self._sync_static_configs()

    def _sync_static_configs(self) -> None:
        instruments: list[EtfInstrument] = []
        for symbol in self.settings.etf_list:
            normalized = normalize_symbol(symbol)
            market, code = split_symbol(normalized)
            instruments.append(
                EtfInstrument(
                    symbol=normalized,
                    market=market,
                    code=code,
                    name=normalized,
                    benchmark_index=self._benchmark_from_mapping(normalized),
                )
            )
        self.repository.replace_instruments(instruments)
        self.repository.replace_index_mappings(self.settings.index_proxy_map)

    def _benchmark_from_mapping(self, symbol: str) -> str:
        for index_symbol, proxies in self.settings.index_proxy_map.items():
            if symbol in [normalize_symbol(p) for p in proxies]:
                return index_symbol
        market, code = split_symbol(symbol)
        if market.value == "INDEX":
            return code
        return ""

    def run(
        self,
        task_id: str,
        symbols: list[str] | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
    ) -> list[EtfAnalysisResult]:
        normalized_symbols = [
            normalize_symbol(s) for s in (symbols or self.settings.etf_list)
        ]
        results: list[EtfAnalysisResult] = []
        for symbol in normalized_symbols:
            market, code = split_symbol(symbol)
            if (
                not skip_market_guard
                and market.value.lower() in {"cn", "hk", "us"}
                and not is_market_open_today(market)
            ):
                logger.info(
                    "Skipping %s because market %s is closed today",
                    symbol,
                    market.value,
                )
                continue
            try:
                bars, _ = self.fetcher_manager.get_daily_bars(symbol=symbol, days=120)
                self.repository.save_daily_bars(bars)
                quote, _ = self.fetcher_manager.get_realtime_quote(symbol=symbol)
                if quote is not None:
                    self.repository.save_realtime_quote(quote)

                factors = compute_factors(bars=bars, quote=quote)
                benchmark = self._benchmark_from_mapping(symbol) or code
                news, provider_name = self.news_manager.search(
                    query=f"{benchmark} ETF market outlook",
                    max_results=5,
                    days=self.settings.news_max_age_days,
                )
                context = EtfAnalysisContext(
                    symbol=symbol,
                    market=market,
                    code=code,
                    benchmark_index=benchmark,
                    factors={
                        **factors,
                        "news_provider": provider_name,
                        "force_refresh": force_refresh,
                    },
                    latest_quote=quote,
                    latest_bar=bars[-1] if bars else None,
                    news_items=[
                        {
                            "title": item.title,
                            "url": item.url,
                            "snippet": item.snippet,
                            "source": item.source,
                            "published_at": item.published_at.isoformat()
                            if item.published_at
                            else None,
                        }
                        for item in news
                    ],
                )
                result = self.analyzer.analyze(context)
                trade_date = bars[-1].trade_date if bars else date.today()
                self.repository.save_analysis_report(
                    task_id=task_id,
                    symbol=symbol,
                    trade_date=trade_date,
                    factors=context.factors,
                    result=result,
                )
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Pipeline failed for %s: %s", symbol, exc)
                fallback = EtfAnalysisResult.neutral_fallback(symbol, str(exc))
                self.repository.save_analysis_report(
                    task_id=task_id,
                    symbol=symbol,
                    trade_date=date.today(),
                    factors={"data_quality": "error"},
                    result=fallback,
                )
                results.append(fallback)
        return results
