from __future__ import annotations

import importlib
import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.cli.run_daily_analysis import run_daily_analysis
from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisResult,
    EtfDailyBar,
    EtfRealtimeQuote,
    Trend,
)
from daily_etf_analysis.notifications.base import (
    NotificationDispatchResult,
    NotificationResult,
)
from daily_etf_analysis.services import AnalysisService

_FIXED_TRADE_DATE = date(2026, 3, 10)


class _DeterministicFetcher:
    def get_daily_bars(self, symbol: str, days: int = 120):  # type: ignore[no-untyped-def]
        bars: list[EtfDailyBar] = []
        start = _FIXED_TRADE_DATE - timedelta(days=34)
        for idx in range(35):
            value = 100.0 + float(idx)
            bars.append(
                EtfDailyBar(
                    symbol=symbol,
                    trade_date=start + timedelta(days=idx),
                    open=value,
                    high=value + 1.0,
                    low=value - 1.0,
                    close=value + 0.5,
                    volume=1000.0 + idx,
                    amount=100000.0 + float(idx * 100),
                    pct_chg=0.01,
                    source="stub-fetcher",
                )
            )
        return bars, "stub-fetcher"

    def get_realtime_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        return (
            EtfRealtimeQuote(
                symbol=symbol,
                price=135.5,
                change_pct=0.02,
                turnover=2000000.0,
                volume=12000.0,
                amount=3000000.0,
                quote_time=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
                source="stub-fetcher",
            ),
            "stub-fetcher",
        )


class _DeterministicNews:
    def search(self, query: str, max_results: int = 5, days: int = 3):  # type: ignore[no-untyped-def]
        return (
            [
                SimpleNamespace(
                    title="Tech ETF momentum",
                    url="https://example.com/news/tech-momentum",
                    snippet="Momentum remains strong.",
                    source="stub-news",
                    published_at=datetime(2026, 3, 10, 9, 30, tzinfo=UTC),
                )
            ],
            "stub-news",
        )


class _DeterministicAnalyzer:
    def analyze(self, context):  # type: ignore[no-untyped-def]
        return EtfAnalysisResult(
            symbol=context.symbol,
            score=88,
            trend=Trend.BULLISH,
            action=Action.BUY,
            confidence=Confidence.HIGH,
            summary="Synthetic bullish signal for integration test.",
            key_points=["Price above medium-term trend."],
            risk_alerts=[],
            model_used="stub/model",
            success=True,
        )


class _NotifierSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send_markdown(self, title: str, markdown: str) -> NotificationDispatchResult:
        self.calls.append({"title": title, "markdown": markdown})
        return NotificationDispatchResult(
            sent=True,
            reason="ok",
            channel_results={"stub": NotificationResult(sent=True, reason="ok")},
        )


def _build_real_service(tmp_path: Path) -> AnalysisService:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'e2e_flow.db'}",
        etf_list=["US:QQQ"],
        index_proxy_map={"NDX": ["US:QQQ"]},
        notify_channels=[],
    )
    service = AnalysisService(settings=settings)
    service.pipeline.fetcher_manager = _DeterministicFetcher()  # type: ignore[assignment]
    service.pipeline.news_manager = _DeterministicNews()  # type: ignore[assignment]
    service.pipeline.analyzer = _DeterministicAnalyzer()  # type: ignore[assignment]
    service.task_manager.pipeline = service.pipeline
    return service


def _wait_run_completed(
    client: TestClient, run_id: str, timeout_seconds: float = 8.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        resp = client.get(f"/api/v1/analysis/runs/{run_id}")
        assert resp.status_code == 200
        payload = resp.json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not finish within timeout")


def test_api_end_to_end_analysis_pipeline_and_history(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    settings_module = importlib.import_module("daily_etf_analysis.config.settings")
    monkeypatch.delenv("API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    settings_module.reload_settings()
    monkeypatch.setattr(
        "daily_etf_analysis.pipelines.daily_pipeline.is_market_open_today",
        lambda _market: True,
    )

    service = _build_real_service(tmp_path)

    def _service_override() -> AnalysisService:
        return service

    _service_override.cache_info = lambda: SimpleNamespace(currsize=1)  # type: ignore[attr-defined]
    _service_override.cache_clear = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(router_module, "_service", _service_override)
    monkeypatch.setattr(app_module, "shutdown_service", lambda: None)

    client = TestClient(app)
    run_resp = client.post(
        "/api/v1/analysis/runs",
        json={"symbols": ["US:QQQ"], "force_refresh": True},
    )
    assert run_resp.status_code == 202
    run_payload = run_resp.json()
    run_id = str(run_payload["run_id"])
    assert run_payload["status"] == "processing"

    run_state = _wait_run_completed(client, run_id)
    assert run_state["status"] == "completed"
    assert run_state["total_tasks"] == 1
    assert run_state["completed_tasks"] == 1

    run_detail_resp = client.get(f"/api/v1/analysis/runs/{run_id}")
    assert run_detail_resp.status_code == 200
    assert run_detail_resp.json()["run_id"] == run_id

    report_resp = client.get(
        "/api/v1/reports/daily",
        params={
            "date": _FIXED_TRADE_DATE.isoformat(),
            "market": "us",
            "run_id": run_id,
        },
    )
    assert report_resp.status_code == 200
    report_payload = report_resp.json()
    assert report_payload["run_summary"]["run_id"] == run_id
    assert len(report_payload["symbol_results"]) == 1
    assert report_payload["symbol_results"][0]["symbol"] == "US:QQQ"
    assert report_payload["symbol_results"][0]["action"] == "buy"

    history_resp = client.get(
        "/api/v1/history/signals",
        params={"symbol": "US:QQQ", "run_id": run_id},
    )
    assert history_resp.status_code == 200
    history_payload = history_resp.json()
    assert len(history_payload["items"]) >= 1
    assert history_payload["items"][0]["symbol"] == "US:QQQ"

    service.shutdown()


def test_cli_end_to_end_run_daily_analysis_with_real_service(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "daily_etf_analysis.pipelines.daily_pipeline.is_market_open_today",
        lambda _market: True,
    )
    service = _build_real_service(tmp_path)
    notifier = _NotifierSpy()
    output_dir = tmp_path / "reports"

    result = run_daily_analysis(
        service=service,
        notifier=notifier,  # type: ignore[arg-type]
        force_run=True,
        symbols=["US:QQQ"],
        market=None,
        skip_notify=False,
        output_dir=output_dir,
        wait_timeout_seconds=8,
        poll_interval_seconds=0.05,
    )
    assert result["status"] == "completed"
    assert result["task_ids"] == [result["task_id"]]
    assert result["notification_sent"] is True
    assert len(notifier.calls) == 1

    report_path = Path(str(result["report_path"]))
    assert report_path.exists()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["status"] == "completed"
    assert len(report_payload["report_rows"]) == 1
    assert report_payload["report_rows"][0]["symbol"] == "US:QQQ"
    assert report_payload["report_rows"][0]["action"] == "buy"

    history_payload = service.list_history(page=1, limit=20, symbol="US:QQQ")
    assert int(history_payload["total"]) >= 1
    assert len(history_payload["items"]) >= 1

    service.shutdown()
