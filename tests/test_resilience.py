from __future__ import annotations

from contextlib import suppress

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.providers.resilience import (
    CircuitBreaker,
    provider_stats_snapshot,
    run_with_resilience,
)


def test_run_with_resilience_retries_then_succeeds() -> None:
    settings = Settings(
        provider_max_retries=2,
        provider_backoff_ms=1,
        provider_circuit_fail_threshold=5,
        provider_circuit_reset_seconds=60,
    )
    circuit_breakers: dict[str, CircuitBreaker] = {}
    attempts = {"count": 0}

    def flaky_call() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary failure")
        return "ok"

    result = run_with_resilience(
        provider="test_retry_provider",
        operation="daily_bars",
        call=flaky_call,
        settings=settings,
        circuit_breakers=circuit_breakers,
        sleep_func=lambda _: None,
    )
    assert result == "ok"
    assert attempts["count"] == 3

    stats = [
        item
        for item in provider_stats_snapshot()
        if item["provider"] == "test_retry_provider"
        and item["operation"] == "daily_bars"
    ]
    assert len(stats) == 1
    assert stats[0]["retry_count"] == 2
    assert stats[0]["success_count"] == 1
    assert stats[0]["failure_count"] == 2
    assert stats[0]["circuit_state"] == "closed"


def test_run_with_resilience_opens_circuit_after_threshold() -> None:
    settings = Settings(
        provider_max_retries=0,
        provider_backoff_ms=0,
        provider_circuit_fail_threshold=2,
        provider_circuit_reset_seconds=60,
    )
    circuit_breakers: dict[str, CircuitBreaker] = {}

    def always_fail() -> str:
        raise RuntimeError("boom")

    for _ in range(2):
        with suppress(RuntimeError):
            run_with_resilience(
                provider="test_circuit_provider",
                operation="realtime_quote",
                call=always_fail,
                settings=settings,
                circuit_breakers=circuit_breakers,
                sleep_func=lambda _: None,
            )

    try:
        run_with_resilience(
            provider="test_circuit_provider",
            operation="realtime_quote",
            call=always_fail,
            settings=settings,
            circuit_breakers=circuit_breakers,
            sleep_func=lambda _: None,
        )
    except RuntimeError as exc:
        assert "Circuit open" in str(exc)
    else:
        raise AssertionError("Expected circuit open error")

    stats = [
        item
        for item in provider_stats_snapshot()
        if item["provider"] == "test_circuit_provider"
        and item["operation"] == "realtime_quote"
    ]
    assert len(stats) == 1
    assert stats[0]["circuit_state"] == "open"
    assert stats[0]["failure_count"] >= 3
