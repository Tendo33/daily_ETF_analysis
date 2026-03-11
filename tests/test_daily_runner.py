from __future__ import annotations

import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from daily_etf_analysis.cli.run_daily_analysis import (
    _exit_code_for_status,
    _wait_tasks_completion,
    parse_cli_args,
    run_daily_analysis,
)
from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import AnalysisTask, TaskStatus
from daily_etf_analysis.notifications.feishu import NotificationResult


class _FakeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.run_calls: list[dict[str, object]] = []
        self.daily_report_calls: list[dict[str, object]] = []
        self.task_report_date: date | None = None
        self._task = AnalysisTask(
            task_id="task-123",
            status=TaskStatus.PENDING,
            symbols=[],
            force_refresh=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._poll_count = 0

    def run_analysis(  # type: ignore[no-untyped-def]
        self,
        symbols=None,
        force_refresh=False,
        skip_market_guard=False,
    ):
        self.run_calls.append(
            {
                "symbols": symbols,
                "force_refresh": force_refresh,
                "skip_market_guard": skip_market_guard,
            }
        )
        self._task.symbols = list(symbols or [])
        self._task.force_refresh = bool(force_refresh)
        self._task.status = TaskStatus.PROCESSING
        return self._task

    def get_task(self, task_id: str):  # type: ignore[no-untyped-def]
        self._poll_count += 1
        if self._poll_count >= 1:
            self._task.status = TaskStatus.COMPLETED
        return self._task

    def get_daily_report(self, target_date: date, market: str | None = None):  # type: ignore[no-untyped-def]
        self.daily_report_calls.append({"target_date": target_date, "market": market})
        return [
            {
                "symbol": "CN:159659",
                "trade_date": target_date.isoformat(),
                "market": market,
                "score": 77,
                "action": "hold",
            }
        ]

    def get_task_report_date(self, task_id: str):  # type: ignore[no-untyped-def]
        return self.task_report_date


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        self.calls.append({"title": title, "markdown": markdown})
        return NotificationResult(sent=True, reason="ok")


def test_parse_cli_args() -> None:
    args = parse_cli_args(
        [
            "--force-run",
            "--symbols",
            "CN:159659,US:QQQ",
            "--market",
            "cn",
            "--skip-notify",
        ]
    )
    assert args.force_run is True
    assert args.symbols == "CN:159659,US:QQQ"
    assert args.market == "cn"
    assert args.skip_notify is True


def test_force_run_help_describes_guard_and_refresh(capsys) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit):
        parse_cli_args(["--help"])
    out = capsys.readouterr().out
    assert "--force-run" in out
    assert "skip trading-day guard and force refresh" in out.lower()


def test_run_daily_analysis_market_filter_and_notify(tmp_path: Path) -> None:
    settings = Settings(
        etf_list=["CN:159659", "US:QQQ", "HK:02800"],
        feishu_webhook_url="https://example.com/webhook",
    )
    service = _FakeService(settings)
    service.task_report_date = date(2026, 3, 6)
    notifier = _FakeNotifier()

    result = run_daily_analysis(
        service=service,
        notifier=notifier,
        force_run=False,
        symbols=None,
        market="cn",
        skip_notify=False,
        output_dir=tmp_path,
        wait_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert service.run_calls[0]["symbols"] == ["CN:159659"]
    assert service.run_calls[0]["skip_market_guard"] is False
    assert result["task_id"] == "task-123"
    assert result["task_ids"] == ["task-123"]
    assert result["status"] == "completed"
    assert Path(str(result["report_path"])).exists()
    assert result["notification_sent"] is True
    assert len(notifier.calls) == 1
    assert service.daily_report_calls[0]["target_date"] == date(2026, 3, 6)


def test_run_daily_analysis_skip_notify(tmp_path: Path) -> None:
    settings = Settings(etf_list=["CN:159659"])
    service = _FakeService(settings)
    notifier = _FakeNotifier()

    result = run_daily_analysis(
        service=service,
        notifier=notifier,
        force_run=True,
        symbols=["CN:159659"],
        market=None,
        skip_notify=True,
        output_dir=tmp_path,
        wait_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert result["status"] == "completed"
    assert service.run_calls[0]["force_refresh"] is True
    assert service.run_calls[0]["skip_market_guard"] is True
    assert result["notification_sent"] is False
    assert result["notification_reason"] == "skipped"
    assert len(notifier.calls) == 0


def test_run_daily_analysis_skips_when_filtered_symbols_empty(tmp_path: Path) -> None:
    settings = Settings(etf_list=["US:QQQ"], feishu_webhook_url="https://example.com")
    service = _FakeService(settings)
    notifier = _FakeNotifier()

    result = run_daily_analysis(
        service=service,
        notifier=notifier,
        force_run=False,
        symbols=None,
        market="cn",
        skip_notify=False,
        output_dir=tmp_path,
        wait_timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert result["status"] == "skipped"
    assert result["task_ids"] == []
    assert result["notification_sent"] is False
    assert result["notification_reason"] == "no_symbols_matched"
    assert result["task_id"] == "skipped"
    assert len(service.run_calls) == 0
    assert len(service.daily_report_calls) == 0
    assert len(notifier.calls) == 0
    assert Path(str(result["report_path"])).exists()


def test_exit_code_for_status() -> None:
    assert _exit_code_for_status("completed") == 0
    assert _exit_code_for_status("skipped") == 0
    assert _exit_code_for_status("failed") == 1


def test_wait_tasks_completion_respects_global_timeout() -> None:
    class _NeverDoneService:
        def get_task(self, task_id: str):  # type: ignore[no-untyped-def]
            return AnalysisTask(
                task_id=task_id,
                status=TaskStatus.PENDING,
                symbols=["CN:159659"],
                force_refresh=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    service = _NeverDoneService()
    start = time.monotonic()
    tasks = _wait_tasks_completion(
        service=service,  # type: ignore[arg-type]
        task_ids=["task-1", "task-2"],
        timeout_seconds=1,
        poll_interval_seconds=0.1,
    )
    elapsed = time.monotonic() - start

    assert len(tasks) == 2
    assert elapsed < 1.7
