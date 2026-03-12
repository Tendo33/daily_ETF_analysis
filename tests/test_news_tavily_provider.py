from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.providers.news.tavily_provider import TavilyProvider


def test_tavily_rotation_and_cache(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []

    class DummyClient:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def search(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(self.api_key)
            return {
                "results": [
                    {
                        "title": "ETF news",
                        "url": "https://example.com",
                        "content": "market update",
                        "published_date": datetime.now(UTC).isoformat(),
                    }
                ]
            }

    monkeypatch.setitem(
        sys.modules, "tavily", SimpleNamespace(TavilyClient=DummyClient)
    )
    settings = Settings(tavily_api_keys=["k1", "k2"])
    provider = TavilyProvider(settings=settings, cache_ttl_seconds=9999)

    first = provider.search("qqq")
    second = provider.search("qqq")  # cache hit, no new call
    third = provider.search("spy")  # new query, rotates key

    assert first and second and third
    assert calls == ["k2", "k1"]


def test_tavily_custom_base_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, str | None] = {}

    class DummyClient:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url

        def search(self, **kwargs):  # type: ignore[no-untyped-def]
            return {"results": []}

    monkeypatch.setitem(
        sys.modules, "tavily", SimpleNamespace(TavilyClient=DummyClient)
    )
    settings = Settings(
        tavily_api_keys=["k1"],
        tavily_base_url="https://tavily.ivanli.cc/api/tavily",
    )
    provider = TavilyProvider(settings=settings, cache_ttl_seconds=0)

    provider.search("qqq")

    assert captured["api_key"] == "k1"
    assert captured["base_url"] == "https://tavily.ivanli.cc/api/tavily"
