from __future__ import annotations

import logging
from collections.abc import Sequence

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.providers.news.base import NewsItem, NewsProvider
from daily_etf_analysis.providers.news.tavily_provider import TavilyProvider

logger = logging.getLogger(__name__)


class NewsProviderManager:
    def __init__(
        self,
        settings: Settings | None = None,
        providers: Sequence[NewsProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if providers is not None:
            self.providers = list(providers)
        else:
            self.providers = self._build_default_providers()

    def _build_default_providers(self) -> list[NewsProvider]:
        provider_map: dict[str, NewsProvider] = {}
        if self.settings.tavily_api_keys:
            provider_map["tavily"] = TavilyProvider(self.settings)
        ordered: list[NewsProvider] = []
        for name in self.settings.news_provider_priority:
            if name in provider_map:
                ordered.append(provider_map[name])
        for provider in provider_map.values():
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    def search(
        self, query: str, max_results: int = 5, days: int = 3
    ) -> tuple[list[NewsItem], str | None]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                items = provider.search(query=query, max_results=max_results, days=days)
                if items:
                    return items, provider.name
                errors.append(f"{provider.name}: empty result")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name}: {exc}")
                logger.warning("News search failed via %s: %s", provider.name, exc)
        if errors:
            logger.warning(
                "All news providers failed for %s: %s", query, "; ".join(errors)
            )
        return [], None
