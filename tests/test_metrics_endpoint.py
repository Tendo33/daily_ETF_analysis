from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.config.settings import reload_settings


class _FakeService:
    def run_analysis(self, symbols=None, force_refresh=False, skip_market_guard=False):  # type: ignore[no-untyped-def]
        raise AssertionError("not used")


def test_metrics_endpoint_exposes_prometheus_text(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("METRICS_ENABLED", "true")
    reload_settings()

    metrics_module = importlib.import_module("daily_etf_analysis.observability.metrics")
    metrics_module.reset_metrics()

    client = TestClient(app)
    _ = client.get("/api/health")

    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    body = resp.text
    assert "api_requests_total" in body
    assert "analysis_task_total" in body
    assert "provider_calls_total" in body
    assert "notification_delivery_total" in body
    assert "scheduler_runs_total" in body
    assert "report_render_total" in body
    assert "md2img_total" in body


def test_metrics_endpoint_disabled_returns_404(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("METRICS_ENABLED", "false")
    reload_settings()

    client = TestClient(app)
    resp = client.get("/api/metrics")
    assert resp.status_code == 404

    monkeypatch.setenv("METRICS_ENABLED", "true")
    reload_settings()
