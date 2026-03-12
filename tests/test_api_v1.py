from __future__ import annotations

import importlib
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.domain import IndexComparisonResult, IndexComparisonRow


class _FakeService:
    def __init__(self) -> None:
        self.run_calls = 0

    def create_analysis_run(self, **kwargs):  # type: ignore[no-untyped-def]
        self.run_calls += 1
        symbols = kwargs.get("symbols") or ["CN:159659"]
        if kwargs.get("markets") == ["cn"] and symbols == ["US:QQQ"]:
            raise ValueError("No symbols resolved for run.")
        return SimpleNamespace(
            run_id="run-1",
            status=SimpleNamespace(value="processing"),
        )

    def build_run_contract(self, run_id: str):  # type: ignore[no-untyped-def]
        if run_id != "run-1":
            return None
        now = datetime.now(UTC).isoformat()
        return {
            "run_id": "run-1",
            "status": "processing",
            "source": "api",
            "market": "all",
            "run_window": "all:2026-03-11",
            "symbols": ["CN:159659"],
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "total_tasks": 1,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "decision_quality": {"total": 1, "success_rate": 0.0},
            "failures": [],
            "audit_logs": [],
        }

    def refresh_analysis_run(self, run_id: str):  # type: ignore[no-untyped-def]
        return self.build_run_contract(run_id)

    def get_daily_report_contract(self, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "run_summary": {
                "run_id": kwargs.get("run_id"),
                "date": "2026-03-10",
                "market": kwargs.get("market", "all"),
                "total_symbols": 1,
                "generated_at": "2026-03-11",
            },
            "symbol_results": [
                {
                    "run_id": kwargs.get("run_id", "run-1"),
                    "symbol": "CN:159659",
                    "action": "hold",
                    "confidence": "low",
                    "horizon": "next_trading_day",
                    "risk_alerts": [],
                    "rationale": "fallback",
                    "degraded": True,
                    "fallback_reason": "NEUTRAL_FALLBACK",
                }
            ],
            "decision_quality": {
                "total": 1,
                "degraded_count": 1,
                "fallback_count": 1,
                "success_rate": 0.0,
            },
            "failures": [],
        }

    def list_history_signals(self, **kwargs):  # type: ignore[no-untyped-def]
        symbol = kwargs.get("symbol")
        if symbol == "XX:123":
            raise ValueError("invalid symbol")
        return [
            {
                "run_id": kwargs.get("run_id", "run-1"),
                "symbol": symbol or "CN:159659",
                "trade_date": "2026-03-10",
                "action": "hold",
            }
        ]

    def list_etfs(self):  # type: ignore[no-untyped-def]
        return []

    def replace_etfs(self, symbols):  # type: ignore[no-untyped-def]
        return []

    def get_index_mappings(self):  # type: ignore[no-untyped-def]
        return {"NDX": ["US:QQQ"]}

    def replace_index_mappings(self, mapping):  # type: ignore[no-untyped-def]
        return mapping

    def get_quote(self, symbol):  # type: ignore[no-untyped-def]
        return {"symbol": symbol, "price": 1.0}

    def get_history(self, symbol, days=120):  # type: ignore[no-untyped-def]
        return [
            {
                "symbol": symbol,
                "trade_date": date.today().isoformat(),
                "close": 1.0,
            }
        ]

    def get_index_comparison(self, index_symbol, target_date=None):  # type: ignore[no-untyped-def]
        if index_symbol == "MISSING":
            raise ValueError("No ETF mapping found for MISSING")
        report_date = target_date or date.today()
        return IndexComparisonResult(
            index_symbol=index_symbol,
            report_date=report_date,
            rows=[
                IndexComparisonRow(
                    symbol="US:QQQ",
                    market="US",
                    score=88,
                    action="buy",
                    confidence="high",
                    latest_price=111.1,
                    change_pct=1.2,
                    return_20=0.11,
                    return_60=0.24,
                    rank=1,
                    model_used="openai/gpt-4o-mini",
                    success=True,
                )
            ],
        )

    def get_provider_health(self):  # type: ignore[no-untyped-def]
        return [
            {
                "provider": "efinance",
                "operation": "daily_bars",
                "success_count": 2,
                "failure_count": 1,
                "retry_count": 1,
                "circuit_state": "closed",
                "last_error": None,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        ]

    def cleanup_data_lifecycle(self, *, dry_run: bool, actor: str):  # type: ignore[no-untyped-def]
        return {
            "dry_run": dry_run,
            "actor": actor,
            "executed_at": datetime.now(UTC).isoformat(),
            "retention_days": {"tasks": 30, "reports": 60, "quotes": 14},
            "impacted": {"tasks": 0, "reports": 0, "quotes": 0},
            "deleted": {"tasks": 0, "reports": 0, "quotes": 0},
        }


class _FakeRuntime:
    def __init__(self, service: _FakeService) -> None:
        self._service = service
        self.closed = False

    def get_service(self) -> _FakeService:
        return self._service

    def shutdown(self) -> None:
        self.closed = True


@pytest.fixture
def client_with_fake_service(monkeypatch):  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()

    fake_service = _FakeService()
    runtime = _FakeRuntime(fake_service)
    monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)
    with TestClient(app_module.app) as client:
        yield client, fake_service


def test_api_v1_core_endpoints(client_with_fake_service) -> None:
    client, _ = client_with_fake_service

    create_resp = client.post("/api/v1/analysis/runs", json={"symbols": ["CN:159659"]})
    assert create_resp.status_code == 202
    assert create_resp.json()["run_id"] == "run-1"

    run_resp = client.get("/api/v1/analysis/runs/run-1")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "processing"

    refresh_resp = client.post("/api/v1/analysis/runs/run-1/refresh")
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["run_id"] == "run-1"

    report_resp = client.get(
        "/api/v1/reports/daily",
        params={"date": date.today().isoformat(), "market": "all"},
    )
    assert report_resp.status_code == 200
    assert report_resp.json()["decision_quality"]["degraded_count"] == 1

    history_signals = client.get(
        "/api/v1/history/signals", params={"symbol": "CN:159659"}
    )
    assert history_signals.status_code == 200
    assert history_signals.json()["items"][0]["symbol"] == "CN:159659"

    quote_resp = client.get("/api/v1/etfs/CN:159659/quote")
    assert quote_resp.status_code == 200
    assert quote_resp.json()["price"] == 1.0

    history_resp = client.get("/api/v1/etfs/CN:159659/history?days=0")
    assert history_resp.status_code == 422

    compare_resp = client.get(
        f"/api/v1/index-comparisons?index_symbol=NDX&date={date.today().isoformat()}"
    )
    assert compare_resp.status_code == 200
    assert compare_resp.json()["index_symbol"] == "NDX"

    compare_not_found = client.get(
        f"/api/v1/index-comparisons?index_symbol=MISSING&date={date.today().isoformat()}"
    )
    assert compare_not_found.status_code == 404

    provider_health = client.get("/api/v1/system/provider-health")
    assert provider_health.status_code == 200
    assert provider_health.json()[0]["provider"] == "efinance"

    lifecycle_resp = client.post("/api/v1/system/lifecycle/cleanup?dry_run=true")
    assert lifecycle_resp.status_code == 200
    assert lifecycle_resp.json()["dry_run"] is True


def test_removed_endpoints_return_404(client_with_fake_service) -> None:
    client, _ = client_with_fake_service

    removed_paths = [
        ("post", "/api/v1/analysis/run"),
        ("get", "/api/v1/analysis/tasks"),
        ("get", "/api/v1/analysis/tasks/task-1"),
        ("get", "/api/v1/analysis/status/task-1"),
        ("get", "/api/v1/analysis/tasks/stream"),
        ("get", "/api/v1/history"),
        ("get", "/api/v1/history/1"),
        ("get", "/api/v1/history/1/news"),
    ]

    for method, path in removed_paths:
        if method == "post":
            response = client.post(path, json={"symbols": ["CN:159659"]})
        else:
            response = client.get(path)
        assert response.status_code == 404


def test_create_run_without_resolved_symbols_returns_422(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()

    fake_service = _FakeService()
    runtime = _FakeRuntime(fake_service)
    monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)
    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/v1/analysis/runs",
            json={"markets": ["cn"], "symbols": ["US:QQQ"]},
        )
        assert resp.status_code == 422
        payload = resp.json()["detail"]
        assert payload["code"] == "INVALID_RUN_REQUEST"
        assert fake_service.run_calls == 1


def test_run_not_found_and_invalid_history_symbol(client_with_fake_service) -> None:
    client, _ = client_with_fake_service

    not_found = client.get("/api/v1/analysis/runs/missing")
    assert not_found.status_code == 404
    assert not_found.json()["detail"]["code"] == "RUN_NOT_FOUND"

    invalid_history = client.get("/api/v1/history/signals", params={"symbol": "XX:123"})
    assert invalid_history.status_code == 422
    assert invalid_history.json()["detail"]["code"] == "INVALID_HISTORY_QUERY"


def test_health() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_auth_required_when_enabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    settings_module.reload_settings()
    try:
        fake_service = _FakeService()
        runtime = _FakeRuntime(fake_service)
        monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)
        with TestClient(app_module.app) as client:
            run_resp = client.post(
                "/api/v1/analysis/runs", json={"symbols": ["CN:159659"]}
            )
            assert run_resp.status_code == 401

            run_forbidden = client.post(
                "/api/v1/analysis/runs",
                json={"symbols": ["CN:159659"]},
                headers={"Authorization": "Bearer wrong"},
            )
            assert run_forbidden.status_code == 403

            headers = {"Authorization": "Bearer secret-token"}
            run_ok = client.post(
                "/api/v1/analysis/runs",
                json={"symbols": ["CN:159659"]},
                headers=headers,
            )
            assert run_ok.status_code == 202

            etfs_resp = client.put("/api/v1/etfs", json={"symbols": ["CN:159659"]})
            assert etfs_resp.status_code == 401

            etfs_ok = client.put(
                "/api/v1/etfs",
                json={"symbols": ["CN:159659"]},
                headers=headers,
            )
            assert etfs_ok.status_code == 200

            history_resp = client.get("/api/v1/history/signals")
            assert history_resp.status_code == 401
            history_ok = client.get("/api/v1/history/signals", headers=headers)
            assert history_ok.status_code == 200
    finally:
        monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
        monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
        settings_module.reload_settings()
