from __future__ import annotations

from datetime import datetime

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.providers.news.base import NewsItem
from daily_etf_analysis.services.theme_intel_aggregator import (
    ThemeIntelligenceAggregator,
)


class _FakeNewsManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, max_results: int = 5, days: int = 3):  # type: ignore[no-untyped-def]
        self.calls.append(query)
        items = [
            NewsItem(
                title="政策支持航空航天产业",
                url="https://example.com/a",
                snippet="行业利好持续",
                source="mock",
                published_at=datetime(2026, 3, 10),
            ),
            NewsItem(
                title="航空航天公司订单增长",
                url="https://example.com/b",
                snippet="订单超预期",
                source="mock",
                published_at=datetime(2026, 3, 11),
            ),
        ]
        return items[:max_results], "mock"


def test_theme_intel_aggregator_builds_summary() -> None:
    settings = Settings(theme_intel_enabled=True)
    manager = _FakeNewsManager()
    aggregator = ThemeIntelligenceAggregator(settings=settings, news_manager=manager)  # type: ignore[arg-type]
    summary = aggregator.build(
        symbol="CN:159392",
        theme_tags=["航空航天"],
        benchmark_index="CN",
    )
    assert summary["enabled"] is True
    assert summary["positive_catalysts"]
    assert summary["sentiment_summary"] in {"偏正面", "中性", "偏负面"}
