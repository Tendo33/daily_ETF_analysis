from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.trading_calendar import is_market_open_today
from daily_etf_analysis.domain import (
    EtfAnalysisContext,
    EtfAnalysisResult,
    EtfDailyBar,
    EtfInstrument,
    EtfRealtimeQuote,
    normalize_symbol,
    split_symbol,
)
from daily_etf_analysis.llm import EtfAnalyzer
from daily_etf_analysis.providers.market_data import DataFetcherManager
from daily_etf_analysis.providers.news import NewsProviderManager
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.factor_engine import compute_factors

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineRunOutcome:
    analyzed_count: int
    skipped_count: int
    skipped_symbols: list[str]
    skip_reason: str | None = None


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
        run_id: str | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> PipelineRunOutcome:
        normalized_symbols = [
            normalize_symbol(s) for s in (symbols or self.settings.etf_list)
        ]
        results: list[EtfAnalysisResult] = []
        skipped_symbols: list[str] = []
        skip_reason: str | None = None
        for symbol in normalized_symbols:
            if cancel_event is not None and cancel_event.is_set():
                skip_reason = "Task cancelled before completion"
                break
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
                skipped_symbols.append(symbol)
                continue
            try:
                bars, _ = self.fetcher_manager.get_daily_bars(symbol=symbol, days=120)
                if cancel_event is not None and cancel_event.is_set():
                    skip_reason = "Task cancelled before completion"
                    break
                self.repository.save_daily_bars(bars)
                quote, _ = self.fetcher_manager.get_realtime_quote(symbol=symbol)
                if quote is not None:
                    if cancel_event is not None and cancel_event.is_set():
                        skip_reason = "Task cancelled before completion"
                        break
                    self.repository.save_realtime_quote(quote)

                factors = compute_factors(bars=bars, quote=quote)
                market_snapshot = _build_market_snapshot(
                    bars=bars, quote=quote, factors=factors
                )
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
                if cancel_event is not None and cancel_event.is_set():
                    skip_reason = "Task cancelled before completion"
                    break
                result = self.analyzer.analyze(context)
                if cancel_event is not None and cancel_event.is_set():
                    skip_reason = "Task cancelled before completion"
                    break
                trade_date = bars[-1].trade_date if bars else date.today()
                self.repository.save_analysis_report(
                    task_id=task_id,
                    run_id=run_id,
                    symbol=symbol,
                    trade_date=trade_date,
                    factors=context.factors,
                    result=result,
                    context_snapshot=_build_context_snapshot(
                        symbol=symbol,
                        market=market.value,
                        benchmark_index=benchmark,
                        force_refresh=force_refresh,
                        news_provider=provider_name,
                        market_snapshot=market_snapshot,
                        llm_payload=result.llm_payload,
                    ),
                    news_items=context.news_items,
                )
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                if cancel_event is not None and cancel_event.is_set():
                    skip_reason = "Task cancelled before completion"
                    break
                logger.exception("Pipeline failed for %s: %s", symbol, exc)
                fallback = EtfAnalysisResult.neutral_fallback(symbol, str(exc))
                fallback.fallback_reason = "PROVIDER_FAILED"
                self.repository.save_analysis_report(
                    task_id=task_id,
                    run_id=run_id,
                    symbol=symbol,
                    trade_date=date.today(),
                    factors={"data_quality": "error"},
                    result=fallback,
                    context_snapshot=_build_context_snapshot(
                        symbol=symbol,
                        market=market.value,
                        benchmark_index=self._benchmark_from_mapping(symbol) or code,
                        force_refresh=force_refresh,
                        news_provider=None,
                        market_snapshot={},
                        llm_payload={},
                    ),
                    news_items=[],
                )
                results.append(fallback)
        return PipelineRunOutcome(
            analyzed_count=len(results),
            skipped_count=len(skipped_symbols),
            skipped_symbols=skipped_symbols,
            skip_reason=skip_reason,
        )


def _build_context_snapshot(
    *,
    symbol: str,
    market: str,
    benchmark_index: str,
    force_refresh: bool,
    news_provider: str | None,
    market_snapshot: dict[str, object] | None = None,
    llm_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "market": market,
        "benchmark_index": benchmark_index,
        "force_refresh": force_refresh,
        "news_provider": news_provider,
        "market_snapshot": market_snapshot or {},
        "llm_payload": llm_payload or {},
    }


def _build_market_snapshot(
    *,
    bars: list[EtfDailyBar],
    quote: EtfRealtimeQuote | None,
    factors: dict[str, object],
) -> dict[str, object]:
    latest_bar = bars[-1] if bars else None
    prev_bar = bars[-2] if len(bars) > 1 else None
    close = latest_bar.close if latest_bar else None
    prev_close = prev_bar.close if prev_bar else None
    open_price = latest_bar.open if latest_bar else None
    high = latest_bar.high if latest_bar else None
    low = latest_bar.low if latest_bar else None
    pct_chg = (
        latest_bar.pct_chg
        if latest_bar and latest_bar.pct_chg is not None
        else _pct_change(prev_close, close)
    )
    change_amount = None
    amplitude = None
    if close is not None and prev_close:
        change_amount = close - prev_close
        if high is not None and low is not None and prev_close:
            amplitude = (high - low) / prev_close * 100
    price = quote.price if quote is not None else close
    return {
        "close": close,
        "prev_close": prev_close,
        "open": open_price,
        "high": high,
        "low": low,
        "pct_chg": pct_chg,
        "change_amount": change_amount,
        "amplitude": amplitude,
        "volume": latest_bar.volume if latest_bar else None,
        "amount": latest_bar.amount if latest_bar else None,
        "price": price,
        "volume_ratio": factors.get("volume_ratio"),
        "turnover_rate": factors.get("turnover"),
        "source": (quote.source if quote is not None else None)
        or (latest_bar.source if latest_bar else None),
    }


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return (end - start) / start * 100
