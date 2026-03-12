from __future__ import annotations

import sys

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.providers.news.tavily_provider import TavilyProvider

QUERY = "特朗普是什么时候访华"
MAX_RESULTS = 5
DAYS = 3


def main() -> int:
    settings = Settings()
    if not settings.tavily_api_keys:
        print(
            "ERROR: TAVILY_API_KEYS not configured. Set it in .env or env vars.",
            file=sys.stderr,
        )
        return 2

    provider = TavilyProvider(settings=settings, cache_ttl_seconds=0)
    try:
        items = provider.search(QUERY, max_results=MAX_RESULTS, days=DAYS)
    except Exception as exc:
        print(f"ERROR: Tavily search failed: {exc!r}", file=sys.stderr)
        return 3

    base_url = settings.tavily_base_url or "<default>"
    print(f"Query: {QUERY}")
    print(f"Base URL: {base_url}")
    print(f"Results: {len(items)}")
    if not items:
        return 0

    for idx, item in enumerate(items, start=1):
        print(f"{idx}. {item.title}")
        print(f"   url: {item.url}")
        if item.published_at is not None:
            print(f"   published_at: {item.published_at.isoformat()}")
        if item.snippet:
            print(f"   snippet: {item.snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
