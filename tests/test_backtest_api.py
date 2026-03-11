from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app


class _FakeBacktestService:
    def run_backtest(  # type: ignore[no-untyped-def]
        self, symbols=None, eval_window_days=20
    ):
        if eval_window_days < 1:
            raise ValueError("eval_window_days must be >= 1")
        return {
            "run": {
                "run_id": "run-1",
                "eval_window_days": eval_window_days,
                "total_samples": 2,
                "evaluated_samples": 2,
                "skipped_count": 0,
                "direction_hit_rate": 0.5,
                "avg_return": 0.01,
                "max_drawdown": -0.18,
                "win_rate": 0.5,
                "disclaimer": "For research only; not investment advice.",
            },
            "results": [
                {
                    "symbol": "US:QQQ",
                    "sample_count": 2,
                    "evaluated_count": 2,
                    "skipped_count": 0,
                    "direction_hit_rate": 0.5,
                    "avg_return": 0.01,
                    "max_drawdown": -0.18,
                    "win_rate": 0.5,
                }
            ],
        }

    def get_backtest_results(self, run_id: str):  # type: ignore[no-untyped-def]
        if run_id != "run-1":
            return None
        return [
            {
                "symbol": "US:QQQ",
                "sample_count": 2,
                "evaluated_count": 2,
                "skipped_count": 0,
                "direction_hit_rate": 0.5,
                "avg_return": 0.01,
                "max_drawdown": -0.18,
                "win_rate": 0.5,
            }
        ]

    def get_backtest_performance(self, run_id: str):  # type: ignore[no-untyped-def]
        if run_id != "run-1":
            return None
        return {
            "run_id": "run-1",
            "direction_hit_rate": 0.5,
            "avg_return": 0.01,
            "max_drawdown": -0.18,
            "win_rate": 0.5,
            "disclaimer": "For research only; not investment advice.",
        }

    def get_backtest_symbol_performance(self, run_id: str, symbol: str):  # type: ignore[no-untyped-def]
        if run_id != "run-1" or symbol != "US:QQQ":
            return None
        return {
            "symbol": "US:QQQ",
            "direction_hit_rate": 0.5,
            "avg_return": 0.01,
            "max_drawdown": -0.18,
            "win_rate": 0.5,
        }


class _InvalidSymbolBacktestService(_FakeBacktestService):
    def get_backtest_symbol_performance(self, run_id: str, symbol: str):  # type: ignore[no-untyped-def]
        raise ValueError(f"invalid symbol: {symbol}")


def test_backtest_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    monkeypatch.setattr(router_module, "_service", lambda: _FakeBacktestService())

    client = TestClient(app)

    run_resp = client.post(
        "/api/v1/backtest/run",
        json={"symbols": ["US:QQQ"], "eval_window_days": 20},
    )
    assert run_resp.status_code == 200
    assert run_resp.json()["run"]["run_id"] == "run-1"

    results_resp = client.get("/api/v1/backtest/results?run_id=run-1")
    assert results_resp.status_code == 200
    assert results_resp.json()[0]["symbol"] == "US:QQQ"

    perf_resp = client.get("/api/v1/backtest/performance?run_id=run-1")
    assert perf_resp.status_code == 200
    assert "disclaimer" in perf_resp.json()

    symbol_resp = client.get("/api/v1/backtest/performance/US:QQQ?run_id=run-1")
    assert symbol_resp.status_code == 200
    assert symbol_resp.json()["symbol"] == "US:QQQ"

    not_found = client.get("/api/v1/backtest/performance?run_id=missing")
    assert not_found.status_code == 404

    invalid_input = client.post(
        "/api/v1/backtest/run",
        json={"symbols": ["US:QQQ"], "eval_window_days": 0},
    )
    assert invalid_input.status_code == 422


def test_backtest_symbol_invalid_symbol_returns_422(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    monkeypatch.setattr(
        router_module,
        "_service",
        lambda: _InvalidSymbolBacktestService(),
    )
    client = TestClient(app)

    resp = client.get("/api/v1/backtest/performance/XX:123?run_id=run-1")
    assert resp.status_code == 422
