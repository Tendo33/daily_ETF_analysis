from __future__ import annotations

import importlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app


class _FakeHistoryService:
    def list_history(  # type: ignore[no-untyped-def]
        self, page=1, limit=20, symbol=None
    ):
        assert page == 1
        assert limit == 20
        assert symbol == "US:QQQ"
        return {
            "items": [
                {
                    "id": 11,
                    "task_id": "task-1",
                    "symbol": "US:QQQ",
                    "trade_date": "2026-03-09",
                    "score": 88,
                    "action": "buy",
                    "confidence": "high",
                    "summary": "good",
                    "success": True,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ],
            "page": 1,
            "limit": 20,
            "total": 1,
        }

    def get_history_detail(self, record_id: int):  # type: ignore[no-untyped-def]
        if record_id != 11:
            return None
        return {
            "id": 11,
            "task_id": "task-1",
            "symbol": "US:QQQ",
            "trade_date": "2026-03-09",
            "score": 88,
            "trend": "bullish",
            "action": "buy",
            "confidence": "high",
            "summary": "good",
            "model_used": "openai/gpt-4o-mini",
            "success": True,
            "error_message": None,
            "factors": {"return_20": 0.1},
            "key_points": ["k1"],
            "risk_alerts": ["r1"],
            "context_snapshot": {"benchmark": "NDX"},
            "news_items": [{"title": "n1"}],
            "created_at": datetime.now(UTC).isoformat(),
        }

    def get_history_news(self, record_id: int):  # type: ignore[no-untyped-def]
        if record_id != 11:
            return None
        return [{"title": "n1", "url": "https://example.com"}]


def test_history_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    monkeypatch.setattr(router_module, "_service", lambda: _FakeHistoryService())
    client = TestClient(app)

    list_resp = client.get("/api/v1/history?page=1&limit=20&symbol=US:QQQ")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == 11

    detail_resp = client.get("/api/v1/history/11")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["context_snapshot"]["benchmark"] == "NDX"

    news_resp = client.get("/api/v1/history/11/news")
    assert news_resp.status_code == 200
    assert news_resp.json()[0]["title"] == "n1"

    missing_detail = client.get("/api/v1/history/999")
    assert missing_detail.status_code == 404

    missing_news = client.get("/api/v1/history/999/news")
    assert missing_news.status_code == 404

    bad_page = client.get("/api/v1/history?page=0")
    assert bad_page.status_code == 422

    bad_limit = client.get("/api/v1/history?limit=999")
    assert bad_limit.status_code == 422


class _InvalidSymbolHistoryService:
    def list_history(  # type: ignore[no-untyped-def]
        self, page=1, limit=20, symbol=None
    ):
        raise ValueError(f"invalid symbol: {symbol}")


def test_history_api_invalid_symbol_returns_422(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    monkeypatch.setattr(
        router_module,
        "_service",
        lambda: _InvalidSymbolHistoryService(),
    )
    client = TestClient(app)

    resp = client.get("/api/v1/history?symbol=XX:123")
    assert resp.status_code == 422
