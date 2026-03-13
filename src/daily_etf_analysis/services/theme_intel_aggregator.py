from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.providers.news import NewsProviderManager
from daily_etf_analysis.providers.news.base import NewsItem

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ThemeIntelSummary:
    payload: dict[str, Any]


class ThemeIntelligenceAggregator:
    def __init__(
        self,
        settings: Settings | None = None,
        news_manager: NewsProviderManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.news_manager = news_manager or NewsProviderManager(self.settings)

    def build(
        self,
        *,
        symbol: str,
        theme_tags: list[str],
        benchmark_index: str,
    ) -> dict[str, Any]:
        if not self.settings.theme_intel_enabled:
            return {
                "enabled": False,
                "reason": "disabled",
                "theme_tags": theme_tags,
            }
        if not theme_tags:
            return {
                "enabled": False,
                "reason": "no_theme_tags",
                "theme_tags": [],
            }

        queries = _build_queries(theme_tags, benchmark_index)
        items: list[NewsItem] = []
        provider: str | None = None
        for query in queries:
            news, provider_name = self.news_manager.search(
                query=query,
                max_results=4,
                days=self.settings.news_max_age_days,
            )
            if provider is None:
                provider = provider_name
            items.extend(news)

        merged = _dedupe_items(items)
        merged = merged[:8]
        summary = _summarize_items(merged)
        summary.update(
            {
                "enabled": True,
                "theme_tags": theme_tags,
                "provider": provider,
                "items_count": len(merged),
                "symbol": symbol,
                "benchmark_index": benchmark_index,
            }
        )
        return summary


def _build_queries(theme_tags: list[str], benchmark_index: str) -> list[str]:
    tag_text = " ".join(theme_tags[:3])
    base = tag_text or benchmark_index
    return [
        f"{base} 行业 动态 政策",
        f"{base} 订单 业绩 资本开支",
        f"{base} 龙头 公司 产业链",
    ]


def _dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        key = (item.url or item.title or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=_sort_news_item, reverse=True)
    return deduped


def _sort_news_item(item: NewsItem) -> datetime:
    if item.published_at:
        return item.published_at
    return datetime.min


def _summarize_items(items: list[NewsItem]) -> dict[str, Any]:
    if not items:
        return {
            "theme_summary": "主题资讯不足，暂无法形成有效聚合。",
            "latest_news": "",
            "positive_catalysts": [],
            "risk_alerts": [],
            "sentiment_summary": "中性",
            "news_briefs": [],
        }

    positives: list[str] = []
    negatives: list[str] = []
    briefs: list[dict[str, Any]] = []
    for item in items:
        title = (item.title or "").strip()
        snippet = (item.snippet or "").strip()
        if title:
            label = _classify_headline(title + " " + snippet)
            if label == "positive":
                positives.append(title)
            elif label == "negative":
                negatives.append(title)
        briefs.append(
            {
                "title": title,
                "snippet": snippet,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at.isoformat()
                if item.published_at
                else None,
            }
        )

    sentiment = "中性"
    if positives and not negatives:
        sentiment = "偏正面"
    elif negatives and not positives:
        sentiment = "偏负面"
    elif len(positives) > len(negatives):
        sentiment = "偏正面"
    elif len(negatives) > len(positives):
        sentiment = "偏负面"

    latest_news = "；".join(
        [title for title in [b["title"] for b in briefs[:2]] if title]
    )

    return {
        "theme_summary": f"主题聚焦：{briefs[0]['title']}" if briefs else "",
        "latest_news": latest_news,
        "positive_catalysts": positives[:3],
        "risk_alerts": negatives[:3],
        "sentiment_summary": sentiment,
        "news_briefs": briefs[:5],
    }


def _classify_headline(text: str) -> str:
    lower = text.lower()
    positive_keywords = [
        "增长",
        "上调",
        "突破",
        "中标",
        "政策支持",
        "订单",
        "利好",
        "盈利",
    ]
    negative_keywords = ["下滑", "下调", "风险", "下跌", "减持", "亏损", "调查", "处罚"]
    for key in positive_keywords:
        if key in lower:
            return "positive"
    for key in negative_keywords:
        if key in lower:
            return "negative"
    return "neutral"
