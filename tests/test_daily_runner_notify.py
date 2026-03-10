from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from daily_etf_analysis.cli.run_daily_analysis import run_daily_analysis
from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import AnalysisTask, TaskStatus
from daily_etf_analysis.notifications.base import (
    NotificationDispatchResult,
    NotificationResult,
)


class _FakeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._task = AnalysisTask(
            task_id="task-xyz",
            status=TaskStatus.COMPLETED,
            symbols=["US:QQQ"],
            force_refresh=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def run_analysis(  # type: ignore[no-untyped-def]
        self, symbols=None, force_refresh=False, skip_market_guard=False
    ):
        return self._task

    def get_task(self, task_id: str):  # type: ignore[no-untyped-def]
        return self._task

    def get_task_report_date(self, task_id: str):  # type: ignore[no-untyped-def]
        return date(2026, 3, 9)

    def get_daily_report(self, target_date: date, market: str | None = None):  # type: ignore[no-untyped-def]
        return [
            {
                "symbol": "US:QQQ",
                "score": 88,
                "action": "buy",
                "risk_alerts": ["volatility rising"],
                "trade_date": target_date.isoformat(),
                "market": market,
            }
        ]


class _FakeManager:
    def send_markdown(self, title: str, markdown: str) -> NotificationDispatchResult:
        return NotificationDispatchResult(
            sent=True,
            reason="ok",
            channel_results={
                "feishu": NotificationResult(sent=True, reason="ok"),
                "telegram": NotificationResult(sent=False, reason="disabled"),
            },
        )


def test_daily_runner_outputs_markdown_and_channel_result(tmp_path: Path) -> None:
    service = _FakeService(Settings(etf_list=["US:QQQ"]))
    result = run_daily_analysis(
        service=service,  # type: ignore[arg-type]
        notifier=_FakeManager(),  # type: ignore[arg-type]
        force_run=False,
        symbols=["US:QQQ"],
        market=None,
        skip_notify=False,
        output_dir=tmp_path,
        wait_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert result["notification_sent"] is True
    assert result["notification_reason"] == "ok"
    assert "notification_channels" in result
    markdown_path = Path(str(result["markdown_report_path"]))
    assert markdown_path.exists()
    assert "report_20260309_task-xyz.md" in markdown_path.name
    legacy_path = tmp_path / "report_20260309.md"
    assert legacy_path.exists()
    text = markdown_path.read_text(encoding="utf-8")
    assert "## Summary" in text
    assert "## Top Symbols" in text
    assert "## Risk Alerts" in text
