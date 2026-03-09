from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timedelta, timezone

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.providers.news.base import NewsItem, NewsProvider


class TavilyProvider(NewsProvider):
    name = "tavily"

    def __init__(self, settings: Settings, cache_ttl_seconds: int = 900) -> None:
        self.settings = settings
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}
        self._keys = deque(settings.tavily_api_keys)

    def _next_key(self) -> str | None:
        if not self._keys:
            return None
        self._keys.rotate(-1)
        return self._keys[0]

    def search(self, query: str, max_results: int = 5, days: int = 3) -> list[NewsItem]:
        now = time.time()
        cache_key = f"{query}|{max_results}|{days}"
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return cached[1]

        key = self._next_key()
        if not key:
            return []

        from tavily import TavilyClient

        client = TavilyClient(api_key=key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
            days=max(1, days),
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        items: list[NewsItem] = []
        for item in response.get("results", []):
            published_raw = item.get("published_date")
            published_at = _parse_datetime(published_raw)
            if published_at is not None and published_at < cutoff:
                continue
            items.append(
                NewsItem(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", "")),
                    published_at=published_at,
                    source="tavily",
                )
            )
        self._cache[cache_key] = (now, items)
        return items


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None
