from __future__ import annotations

from datetime import date

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.domain import AnalysisTask, EtfInstrument, normalize_symbol
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.task_manager import TaskManager


class AnalysisService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = EtfRepository(self.settings)
        self.pipeline = DailyPipeline(
            settings=self.settings, repository=self.repository
        )
        self.task_manager = TaskManager(
            repository=self.repository, pipeline=self.pipeline
        )

    def run_analysis(
        self, symbols: list[str] | None = None, force_refresh: bool = False
    ) -> AnalysisTask:
        target_symbols = [
            normalize_symbol(s) for s in (symbols or self.settings.etf_list)
        ]
        return self.task_manager.submit(target_symbols, force_refresh=force_refresh)

    def list_tasks(self, limit: int = 50) -> list[AnalysisTask]:
        return self.task_manager.list_tasks(limit=limit)

    def get_task(self, task_id: str) -> AnalysisTask | None:
        return self.task_manager.get_task(task_id)

    def list_etfs(self) -> list[EtfInstrument]:
        return self.repository.list_instruments()

    def replace_etfs(self, symbols: list[str]) -> list[EtfInstrument]:
        normalized = [normalize_symbol(s) for s in symbols]
        self.settings.etf_list = normalized
        self.pipeline._sync_static_configs()
        return self.repository.list_instruments()

    def get_index_mappings(self) -> dict[str, list[str]]:
        return self.repository.list_index_mappings()

    def replace_index_mappings(
        self, mapping: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        normalized = {
            str(idx).upper(): [normalize_symbol(symbol) for symbol in symbols]
            for idx, symbols in mapping.items()
        }
        self.settings.index_proxy_map = normalized
        self.repository.replace_index_mappings(normalized)
        return normalized

    def get_quote(self, symbol: str) -> dict[str, str | float | None]:
        normalized = normalize_symbol(symbol)
        quote = self.repository.get_latest_realtime_quote(normalized)
        if not quote:
            quote, _ = self.pipeline.fetcher_manager.get_realtime_quote(normalized)
            if quote:
                self.repository.save_realtime_quote(quote)
        if not quote:
            raise ValueError(f"No quote found for {normalized}")
        return {
            "symbol": quote.symbol,
            "price": quote.price,
            "change_pct": quote.change_pct,
            "turnover": quote.turnover,
            "volume": quote.volume,
            "amount": quote.amount,
            "source": quote.source,
            "quote_time": quote.quote_time.isoformat(),
        }

    def get_history(
        self, symbol: str, days: int = 120
    ) -> list[dict[str, str | float | None]]:
        normalized = normalize_symbol(symbol)
        bars = self.repository.get_recent_bars(normalized, days=days)
        if not bars:
            bars, _ = self.pipeline.fetcher_manager.get_daily_bars(
                normalized, days=days
            )
            self.repository.save_daily_bars(bars)
        return [
            {
                "symbol": b.symbol,
                "trade_date": b.trade_date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "amount": b.amount,
                "pct_chg": b.pct_chg,
                "source": b.source,
            }
            for b in bars
        ]

    def get_daily_report(
        self, target_date: date, market: str | None = None
    ) -> list[dict[str, object]]:
        market_filter = None if market in (None, "all") else market
        return self.repository.get_daily_reports(target_date, market=market_filter)
