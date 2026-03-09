from __future__ import annotations

import importlib
from datetime import date, datetime

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.domain import AnalysisTask, TaskStatus


class _FakeService:
    def __init__(self) -> None:
        self.task = AnalysisTask(
            task_id="task-1",
            status=TaskStatus.PENDING,
            symbols=["CN:159659"],
            force_refresh=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    def run_analysis(self, symbols=None, force_refresh=False):  # type: ignore[no-untyped-def]
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


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
