from __future__ import annotations

from typing import Any


def get_provider_health_snapshot() -> list[dict[str, Any]]:
    # 延迟导入以避免 observability -> providers.resilience 的循环依赖
    from daily_etf_analysis.providers.resilience import provider_stats_snapshot

    return provider_stats_snapshot()
