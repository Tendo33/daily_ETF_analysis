from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app


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


def test_history_signals_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    monkeypatch.setattr(router_module, "_service", lambda: _FakeHistoryService())
    client = TestClient(app)

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
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    monkeypatch.setattr(router_module, "_service", lambda: _FakeHistoryService())
    client = TestClient(app)

    resp = client.get("/api/v1/history/signals?symbol=XX:123")
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "INVALID_HISTORY_QUERY"
