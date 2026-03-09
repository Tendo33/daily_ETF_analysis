from __future__ import annotations

from typing import Any

from daily_etf_analysis.providers.resilience import provider_stats_snapshot


def get_provider_health_snapshot() -> list[dict[str, Any]]:
    return provider_stats_snapshot()
