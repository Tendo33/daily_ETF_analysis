from __future__ import annotations

from datetime import date

from daily_etf_analysis.backtest import BacktestEngine
from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.domain import (
    AnalysisTask,
    EtfInstrument,
    IndexComparisonResult,
    IndexComparisonRow,
    normalize_symbol,
)
from daily_etf_analysis.observability import get_provider_health_snapshot
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline
from daily_etf_analysis.repositories import EtfRepository
from daily_etf_analysis.services.system_config_service import SystemConfigService
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
        self.system_config_service = SystemConfigService(
            settings=self.settings, repository=self.repository
        )
        self.system_config_service.set_on_settings_applied(self._apply_runtime_settings)

    def run_analysis(
        self,
        symbols: list[str] | None = None,
        force_refresh: bool = False,
        skip_market_guard: bool = False,
    ) -> AnalysisTask:
        target_symbols = [
            normalize_symbol(s) for s in (symbols or self.settings.etf_list)
        ]
        return self.task_manager.submit(
            target_symbols,
            force_refresh=force_refresh,
            skip_market_guard=skip_market_guard,
        )

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

    def list_history(
        self, page: int = 1, limit: int = 20, symbol: str | None = None
    ) -> dict[str, object]:
        normalized_symbol = normalize_symbol(symbol) if symbol else None
        items, total = self.repository.list_history(
            page=page, limit=limit, symbol=normalized_symbol
        )
        return {"items": items, "page": page, "limit": limit, "total": total}

    def get_history_detail(self, record_id: int) -> dict[str, object] | None:
        return self.repository.get_history_record(record_id)

    def get_history_news(self, record_id: int) -> list[dict[str, object]] | None:
        record = self.repository.get_history_record(record_id)
        if record is None:
            return None
        news = record.get("news_items", [])
        if isinstance(news, list):
            return [item for item in news if isinstance(item, dict)]
        return []

    def run_backtest(
        self, symbols: list[str] | None = None, eval_window_days: int = 20
    ) -> dict[str, object]:
        if eval_window_days < 1:
            raise ValueError("eval_window_days must be >= 1")

        target_symbols = [
            normalize_symbol(s) for s in (symbols or self.settings.etf_list)
        ]
        engine = BacktestEngine(eval_window_days=eval_window_days)
        signals = self.repository.get_backtest_signals(target_symbols)
        prices = self.repository.get_price_series(target_symbols)
        run_summary, symbol_rows = engine.run(signals=signals, prices_by_symbol=prices)

        disclaimer = "For research only; not investment advice."
        run_id = self.repository.create_backtest_run(
            eval_window_days=eval_window_days,
            symbols=target_symbols,
            disclaimer=disclaimer,
        )
        self.repository.update_backtest_run_summary(
            run_id=run_id,
            total_samples=int(run_summary["total_samples"]),
            evaluated_samples=int(run_summary["evaluated_samples"]),
            skipped_count=int(run_summary["skipped_count"]),
            direction_hit_rate=_to_float_or_none(run_summary["direction_hit_rate"]),
            avg_return=_to_float_or_none(run_summary["avg_return"]),
            max_drawdown=_to_float_or_none(run_summary["max_drawdown"]),
            win_rate=_to_float_or_none(run_summary["win_rate"]),
        )
        self.repository.save_backtest_results(run_id=run_id, results=symbol_rows)
        run = self.repository.get_backtest_run(run_id)
        results = self.repository.get_backtest_results(run_id)
        return {"run": run, "results": results}

    def get_backtest_results(self, run_id: str) -> list[dict[str, object]] | None:
        if self.repository.get_backtest_run(run_id) is None:
            return None
        return self.repository.get_backtest_results(run_id)

    def get_backtest_performance(self, run_id: str) -> dict[str, object] | None:
        return self.repository.get_backtest_run(run_id)

    def get_backtest_symbol_performance(
        self, run_id: str, symbol: str
    ) -> dict[str, object] | None:
        if self.repository.get_backtest_run(run_id) is None:
            return None
        normalized = normalize_symbol(symbol)
        return self.repository.get_backtest_symbol_performance(run_id, normalized)

    def get_system_config(self) -> dict[str, object]:
        return self.system_config_service.get_system_config()

    def validate_system_config(self, updates: dict[str, object]) -> dict[str, object]:
        return self.system_config_service.validate_system_config(updates)

    def update_system_config(
        self, expected_version: int, updates: dict[str, object], actor: str
    ) -> dict[str, object]:
        return self.system_config_service.update_system_config(
            expected_version=expected_version,
            updates=updates,
            actor=actor,
        )

    def get_system_config_schema(self) -> dict[str, object]:
        return self.system_config_service.get_system_config_schema()

    def list_system_config_audit(
        self, page: int = 1, limit: int = 20
    ) -> list[dict[str, object]]:
        return self.system_config_service.list_system_config_audit(
            page=page, limit=limit
        )

    def get_task_report_date(self, task_id: str) -> date | None:
        return self.repository.get_latest_report_trade_date_for_task(task_id)

    def get_index_comparison(
        self, index_symbol: str, target_date: date | None = None
    ) -> IndexComparisonResult:
        normalized_index = index_symbol.strip().upper()
        if not normalized_index:
            raise ValueError("index_symbol is required")

        proxy_symbols = self.repository.get_index_proxy_symbols(normalized_index)
        if not proxy_symbols:
            raise ValueError(f"No ETF mapping found for {normalized_index}")

        latest_reports = self.repository.get_latest_reports_for_symbols(
            symbols=proxy_symbols, report_date=target_date
        )
        latest_quotes = self.repository.get_latest_quotes_for_symbols(proxy_symbols)

        rows: list[IndexComparisonRow] = []
        for symbol in proxy_symbols:
            report = latest_reports.get(symbol)
            if report is None:
                continue
            quote = latest_quotes.get(symbol)
            factors = report.get("factors", {})
            row = IndexComparisonRow(
                symbol=symbol,
                market=symbol.split(":", 1)[0],
                score=int(report.get("score", 50)),
                action=str(report.get("action", "hold")),
                confidence=str(report.get("confidence", "low")),
                latest_price=quote.price
                if quote is not None
                else _to_float_or_none(factors.get("latest_price")),
                change_pct=quote.change_pct
                if quote is not None
                else _to_float_or_none(factors.get("change_pct")),
                return_20=_to_float_or_none(factors.get("return_20")),
                return_60=_to_float_or_none(factors.get("return_60")),
                rank=0,
                model_used=(
                    str(report.get("model_used"))
                    if report.get("model_used") is not None
                    else None
                ),
                success=bool(report.get("success", True)),
            )
            rows.append(row)

        rows.sort(
            key=lambda row: (
                -row.score,
                -_confidence_weight(row.confidence),
                -(row.return_20 if row.return_20 is not None else float("-inf")),
                row.symbol,
            )
        )
        for idx, row in enumerate(rows, start=1):
            row.rank = idx

        if target_date is not None:
            report_date = target_date
        elif latest_reports:
            report_date = max(
                report["trade_date"]
                for report in latest_reports.values()
                if isinstance(report.get("trade_date"), date)
            )
        else:
            report_date = date.today()

        return IndexComparisonResult(
            index_symbol=normalized_index, report_date=report_date, rows=rows
        )

    def get_provider_health(self) -> list[dict[str, object]]:
        return get_provider_health_snapshot()

    def _apply_runtime_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.repository.settings = settings
        self.pipeline = DailyPipeline(settings=settings, repository=self.repository)
        self.task_manager = TaskManager(
            repository=self.repository, pipeline=self.pipeline
        )
        self.system_config_service.settings = settings


def _confidence_weight(value: str) -> int:
    mapping = {"high": 3, "medium": 2, "low": 1}
    return mapping.get(value.lower(), 0)


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
