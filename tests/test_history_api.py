from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


class _FakeHistoryService:
    def list_history_signals(self, **kwargs):  # type: ignore[no-untyped-def]
        symbol = kwargs.get("symbol")
        run_id = kwargs.get("run_id")
        if symbol == "XX:123":
            raise ValueError("invalid symbol")
        return [
            {
                "run_id": run_id or "run-1",
                "symbol": symbol or "US:QQQ",
                "trade_date": "2026-03-09",
                "action": "buy",
                "confidence": "high",
            }
        ]


class _FakeRuntime:
    def __init__(self, service) -> None:  # type: ignore[no-untyped-def]
        self._service = service
        self.closed = False

    def get_service(self):  # type: ignore[no-untyped-def]
        return self._service

    def shutdown(self) -> None:
        self.closed = True


def test_history_signals_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    runtime = _FakeRuntime(_FakeHistoryService())
    monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)
    with TestClient(app_module.app) as client:
        list_resp = client.get(
            "/api/v1/history/signals",
            params={"symbol": "US:QQQ", "run_id": "run-1", "limit": 20},
        )
        assert list_resp.status_code == 200
        payload = list_resp.json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["run_id"] == "run-1"
        assert payload["items"][0]["symbol"] == "US:QQQ"

        bad_limit = client.get("/api/v1/history/signals?limit=99999")
        assert bad_limit.status_code == 422


def test_history_signals_invalid_symbol_returns_422(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    runtime = _FakeRuntime(_FakeHistoryService())
    monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)
    with TestClient(app_module.app) as client:
        resp = client.get("/api/v1/history/signals?symbol=XX:123")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_HISTORY_QUERY"
