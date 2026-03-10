from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from daily_etf_analysis.config.settings import Settings

T = TypeVar("T")


@dataclass(slots=True)
class ProviderCallStats:
    provider: str
    operation: str
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    circuit_state: str = "closed"
    last_error: str | None = None
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "circuit_state": self.circuit_state,
            "last_error": self.last_error,
            "last_updated": self.last_updated.isoformat(),
        }


class CircuitBreaker:
    def __init__(self, fail_threshold: int, reset_seconds: int) -> None:
        self.fail_threshold = max(1, fail_threshold)
        self.reset_seconds = max(1, reset_seconds)
        self._state = "closed"
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if (
                self._state == "open"
                and self._opened_at is not None
                and time.time() - self._opened_at >= self.reset_seconds
            ):
                self._state = "half_open"
            return self._state

    def allow_request(self) -> bool:
        state = self.state
        return state in {"closed", "half_open"}

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            if self._state == "half_open":
                self._state = "open"
                self._failures = self.fail_threshold
                self._opened_at = time.time()
                return

            self._failures += 1
            if self._failures >= self.fail_threshold:
                self._state = "open"
                self._opened_at = time.time()


class ProviderStatsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, ProviderCallStats] = {}

    def _get_or_create(self, provider: str, operation: str) -> ProviderCallStats:
        key = f"{provider}:{operation}"
        if key not in self._stats:
            self._stats[key] = ProviderCallStats(provider=provider, operation=operation)
        return self._stats[key]

    def record_success(self, provider: str, operation: str) -> None:
        with self._lock:
            stat = self._get_or_create(provider, operation)
            stat.success_count += 1
            stat.last_updated = datetime.now(UTC)

    def record_failure(self, provider: str, operation: str, error: str) -> None:
        with self._lock:
            stat = self._get_or_create(provider, operation)
            stat.failure_count += 1
            stat.last_error = error
            stat.last_updated = datetime.now(UTC)

    def record_retry(self, provider: str, operation: str) -> None:
        with self._lock:
            stat = self._get_or_create(provider, operation)
            stat.retry_count += 1
            stat.last_updated = datetime.now(UTC)

    def set_circuit_state(self, provider: str, operation: str, state: str) -> None:
        with self._lock:
            stat = self._get_or_create(provider, operation)
            stat.circuit_state = state
            stat.last_updated = datetime.now(UTC)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                stat.as_dict()
                for stat in sorted(
                    self._stats.values(), key=lambda x: (x.provider, x.operation)
                )
            ]


_STATS_REGISTRY = ProviderStatsRegistry()


def provider_stats_snapshot() -> list[dict[str, Any]]:
    return _STATS_REGISTRY.snapshot()


def run_with_resilience(
    *,
    provider: str,
    operation: str,
    call: Callable[[], T],
    settings: Settings,
    circuit_breakers: dict[str, CircuitBreaker],
    sleep_func: Callable[[float], None] = time.sleep,
) -> T:
    breaker_key = f"{provider}:{operation}"
    breaker = circuit_breakers.setdefault(
        breaker_key,
        CircuitBreaker(
            fail_threshold=settings.provider_circuit_fail_threshold,
            reset_seconds=settings.provider_circuit_reset_seconds,
        ),
    )

    if not breaker.allow_request():
        _STATS_REGISTRY.set_circuit_state(provider, operation, breaker.state)
        error = (
            f"Circuit open for provider={provider}, operation={operation}, "
            "request rejected."
        )
        _STATS_REGISTRY.record_failure(provider, operation, error)
        raise RuntimeError(error)

    retries = 0
    while True:
        try:
            value = call()
            breaker.record_success()
            _STATS_REGISTRY.record_success(provider, operation)
            _STATS_REGISTRY.set_circuit_state(provider, operation, breaker.state)
            return value
        except Exception as exc:  # noqa: BLE001
            breaker.record_failure()
            _STATS_REGISTRY.record_failure(provider, operation, str(exc))
            _STATS_REGISTRY.set_circuit_state(provider, operation, breaker.state)
            if retries >= settings.provider_max_retries:
                raise
            retries += 1
            _STATS_REGISTRY.record_retry(provider, operation)
            backoff_seconds = (
                settings.provider_backoff_ms * (2 ** (retries - 1))
            ) / 1000.0
            if backoff_seconds > 0:
                sleep_func(backoff_seconds)
