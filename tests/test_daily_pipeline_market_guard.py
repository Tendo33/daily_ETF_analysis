from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisResult,
    EtfDailyBar,
    EtfRealtimeQuote,
    Trend,
)
from daily_etf_analysis.pipelines.daily_pipeline import DailyPipeline


class _RepoStub:
    def __init__(self) -> None:
        self.saved_reports: list[dict[str, object]] = []

    def replace_instruments(self, instruments) -> None:  # type: ignore[no-untyped-def]
        return None

    def replace_index_mappings(self, mapping) -> None:  # type: ignore[no-untyped-def]
        return None

    def save_daily_bars(self, bars) -> None:  # type: ignore[no-untyped-def]
        return None

    def save_realtime_quote(self, quote) -> None:  # type: ignore[no-untyped-def]
        return None

    def save_analysis_report(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.saved_reports.append(kwargs)


class _FetcherStub:
    def __init__(self) -> None:
        self.daily_calls = 0
        self.quote_calls = 0

    def get_daily_bars(self, symbol: str, days: int = 120):  # type: ignore[no-untyped-def]
        self.daily_calls += 1
        return (
            [
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=date(2026, 3, 9),
                    open=1.0,
                    high=1.1,
                    low=0.9,
                    close=1.0,
                    source="mock",
                )
            ],
            "mock",
        )

    def get_realtime_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        self.quote_calls += 1
        return (
            EtfRealtimeQuote(
                symbol=symbol,
                price=1.0,
                change_pct=0.1,
                quote_time=datetime.now(UTC),
                source="mock",
            ),
            "mock",
        )


class _NewsStub:
    def search(self, query: str, max_results: int = 5, days: int = 3):  # type: ignore[no-untyped-def]
        return [], "mock"


class _NewsWithItemsStub:
    def search(self, query: str, max_results: int = 5, days: int = 3):  # type: ignore[no-untyped-def]
        return [
            SimpleNamespace(
                title="Macro update",
                url="https://example.com/news/1",
                snippet="Snippet",
                source="mock-news",
                published_at=datetime(2026, 3, 9, tzinfo=UTC),
            )
        ], "mock-news"


class _AnalyzerStub:
    def analyze(self, context):  # type: ignore[no-untyped-def]
        return EtfAnalysisResult(
            symbol=context.symbol,
            score=60,
            trend=Trend.NEUTRAL,
            action=Action.HOLD,
            confidence=Confidence.MEDIUM,
            summary="ok",
            model_used="mock/model",
            success=True,
        )


def _build_pipeline(
    news_manager: object | None = None,
) -> tuple[DailyPipeline, _FetcherStub, _RepoStub]:
    settings = Settings(
        etf_list=["CN:159659"],
        index_proxy_map={"NDX": ["CN:159659"]},
    )
    fetcher = _FetcherStub()
    repo = _RepoStub()
    pipeline = DailyPipeline(
        settings=settings,
        repository=repo,  # type: ignore[arg-type]
        fetcher_manager=fetcher,  # type: ignore[arg-type]
        news_manager=(news_manager or _NewsStub()),  # type: ignore[arg-type]
        analyzer=_AnalyzerStub(),  # type: ignore[arg-type]
    )
    return pipeline, fetcher, repo


def test_pipeline_skips_closed_market_when_guard_enabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "daily_etf_analysis.pipelines.daily_pipeline.is_market_open_today",
        lambda _market: False,
    )
    pipeline, fetcher, repo = _build_pipeline()

    results = pipeline.run(
        task_id="t1",
        symbols=["CN:159659"],
        force_refresh=False,
        skip_market_guard=False,
    )

    assert results == []
    assert fetcher.daily_calls == 0
    assert fetcher.quote_calls == 0
    assert repo.saved_reports == []


def test_pipeline_runs_closed_market_when_guard_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "daily_etf_analysis.pipelines.daily_pipeline.is_market_open_today",
        lambda _market: False,
    )
    pipeline, fetcher, repo = _build_pipeline()

    results = pipeline.run(
        task_id="t2",
        symbols=["CN:159659"],
        force_refresh=True,
        skip_market_guard=True,
    )

    assert len(results) == 1
    assert fetcher.daily_calls == 1
    assert fetcher.quote_calls == 1
    assert len(repo.saved_reports) == 1


def test_pipeline_persists_context_snapshot_and_news(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "daily_etf_analysis.pipelines.daily_pipeline.is_market_open_today",
        lambda _market: True,
    )
    pipeline, _, repo = _build_pipeline(news_manager=_NewsWithItemsStub())

    results = pipeline.run(
        task_id="t3",
        symbols=["CN:159659"],
        force_refresh=True,
        skip_market_guard=False,
    )

    assert len(results) == 1
    saved = repo.saved_reports[0]
    snapshot = saved["context_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["symbol"] == "CN:159659"
    assert snapshot["market"] == "CN"
    assert snapshot["benchmark_index"] == "NDX"
    assert snapshot["force_refresh"] is True
    assert snapshot["news_provider"] == "mock-news"

    news_items = saved["news_items"]
    assert isinstance(news_items, list)
    assert news_items[0]["title"] == "Macro update"
