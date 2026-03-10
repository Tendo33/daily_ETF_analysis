from __future__ import annotations

import importlib
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.domain import (
    AnalysisTask,
    IndexComparisonResult,
    IndexComparisonRow,
    TaskStatus,
)


class _FakeService:
    def __init__(self) -> None:
        self.task = AnalysisTask(
            task_id="task-1",
            status=TaskStatus.PENDING,
            symbols=["CN:159659"],
            force_refresh=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def run_analysis(  # type: ignore[no-untyped-def]
        self, symbols=None, force_refresh=False, skip_market_guard=False
    ):
        self.task.symbols = symbols or self.task.symbols
        return self.task

    def list_tasks(self, limit=50):  # type: ignore[no-untyped-def]
        return [self.task]

    def get_task(self, task_id: str):  # type: ignore[no-untyped-def]
        if task_id == self.task.task_id:
            return self.task
        return None

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
            {"symbol": symbol, "trade_date": date.today().isoformat(), "close": 1.0}
        ]

    def get_daily_report(self, target_date, market=None):  # type: ignore[no-untyped-def]
        return [
            {
                "symbol": "CN:159659",
                "trade_date": target_date.isoformat(),
                "market": market,
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


def test_api_endpoints(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")

    fake_service = _FakeService()
    monkeypatch.setattr(router_module, "_service", lambda: fake_service)
    client = TestClient(app)

    run_resp = client.post("/api/v1/analysis/run", json={"symbols": ["CN:159659"]})
    assert run_resp.status_code == 200
    assert run_resp.json()["task_id"] == "task-1"

    tasks_resp = client.get("/api/v1/analysis/tasks")
    assert tasks_resp.status_code == 200
    assert len(tasks_resp.json()) == 1

    task_resp = client.get("/api/v1/analysis/tasks/task-1")
    assert task_resp.status_code == 200

    quote_resp = client.get("/api/v1/etfs/CN:159659/quote")
    assert quote_resp.status_code == 200
    assert quote_resp.json()["price"] == 1.0

    history_resp = client.get("/api/v1/etfs/CN:159659/history?days=0")
    assert history_resp.status_code == 422

    report_resp = client.get(
        f"/api/v1/reports/daily?date={date.today().isoformat()}&market=all"
    )
    assert report_resp.status_code == 200

    compare_resp = client.get(
        f"/api/v1/index-comparisons?index_symbol=NDX&date={date.today().isoformat()}"
    )
    assert compare_resp.status_code == 200
    assert compare_resp.json()["index_symbol"] == "NDX"
    assert compare_resp.json()["rows"][0]["symbol"] == "US:QQQ"

    compare_not_found = client.get(
        f"/api/v1/index-comparisons?index_symbol=MISSING&date={date.today().isoformat()}"
    )
    assert compare_not_found.status_code == 404

    compare_bad_request = client.get("/api/v1/index-comparisons")
    assert compare_bad_request.status_code == 422

    provider_health = client.get("/api/v1/system/provider-health")
    assert provider_health.status_code == 200
    assert provider_health.json()[0]["provider"] == "efinance"


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_write_endpoints_require_auth_when_enabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")

    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    settings_module.reload_settings()

    fake_service = _FakeService()
    monkeypatch.setattr(router_module, "_service", lambda: fake_service)
    client = TestClient(app)

    run_resp = client.post("/api/v1/analysis/run", json={"symbols": ["CN:159659"]})
    assert run_resp.status_code == 401

    wrong_token = {"Authorization": "Bearer wrong"}
    run_forbidden = client.post(
        "/api/v1/analysis/run",
        json={"symbols": ["CN:159659"]},
        headers=wrong_token,
    )
    assert run_forbidden.status_code == 403

    headers = {"Authorization": "Bearer secret-token"}
    run_ok = client.post(
        "/api/v1/analysis/run",
        json={"symbols": ["CN:159659"]},
        headers=headers,
    )
    assert run_ok.status_code == 200

    etfs_resp = client.put("/api/v1/etfs", json={"symbols": ["CN:159659"]})
    assert etfs_resp.status_code == 401

    etfs_ok = client.put(
        "/api/v1/etfs",
        json={"symbols": ["CN:159659"]},
        headers=headers,
    )
    assert etfs_ok.status_code == 200

    mappings_resp = client.put(
        "/api/v1/index-mappings",
        json={"mappings": {"NDX": ["US:QQQ"]}},
    )
    assert mappings_resp.status_code == 401

    mappings_ok = client.put(
        "/api/v1/index-mappings",
        json={"mappings": {"NDX": ["US:QQQ"]}},
        headers=headers,
    )
    assert mappings_ok.status_code == 200

    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
