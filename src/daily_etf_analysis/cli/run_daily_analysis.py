from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from daily_etf_analysis.domain import AnalysisTask, TaskStatus
from daily_etf_analysis.notifications import FeishuNotifier
from daily_etf_analysis.services import AnalysisService

SKIPPED_STATUS = "skipped"


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily ETF analysis task")
    parser.add_argument("--force-run", action="store_true", help="Force refresh")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols, e.g. CN:159659,US:QQQ",
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        choices=("cn", "hk", "us"),
        help="Limit run to one market",
    )
    parser.add_argument(
        "--skip-notify",
        action="store_true",
        help="Skip Feishu notification",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=int,
        default=900,
        help="Maximum wait time for task completion",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=2.0,
        help="Polling interval for task completion",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory for generated report files",
    )
    return parser.parse_args(argv)


def run_daily_analysis(
    *,
    service: AnalysisService,
    notifier: FeishuNotifier,
    force_run: bool,
    symbols: list[str] | None,
    market: str | None,
    skip_notify: bool,
    output_dir: Path,
    wait_timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    selected_symbols = _resolve_symbols(
        configured_symbols=service.settings.etf_list,
        symbols=symbols,
        market=market,
    )
    report_market = market if market is not None else "all"
    if not selected_symbols:
        report_date = date.today()
        report_path = _write_json_report(
            output_dir=output_dir,
            report_date=report_date,
            task_id=SKIPPED_STATUS,
            payload={
                "task_id": SKIPPED_STATUS,
                "status": SKIPPED_STATUS,
                "report_date": report_date.isoformat(),
                "market": report_market,
                "symbols": selected_symbols,
                "report_rows": [],
            },
        )
        return {
            "task_id": SKIPPED_STATUS,
            "status": SKIPPED_STATUS,
            "report_path": str(report_path),
            "notification_sent": False,
            "notification_reason": "no_symbols_matched",
        }

    task = service.run_analysis(
        symbols=selected_symbols,
        force_refresh=force_run,
    )
    final_task = _wait_task_completion(
        service=service,
        task_id=task.task_id,
        timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    task_status = final_task.status.value

    report_date = service.get_task_report_date(task.task_id) or date.today()
    report_rows = service.get_daily_report(report_date, market=report_market)
    report_path = _write_json_report(
        output_dir=output_dir,
        report_date=report_date,
        task_id=task.task_id,
        payload={
            "task_id": task.task_id,
            "status": task_status,
            "report_date": report_date.isoformat(),
            "market": report_market,
            "symbols": selected_symbols,
            "report_rows": report_rows,
        },
    )

    notification_sent = False
    notification_reason = "skipped" if skip_notify else "disabled"
    if not skip_notify:
        message = _build_markdown_summary(
            task_id=task.task_id,
            status=task_status,
            report_date=report_date,
            market=report_market,
            report_rows=report_rows,
            report_path=report_path,
        )
        notify = notifier.send_markdown(title="daily_ETF_analysis", markdown=message)
        notification_sent = notify.sent
        notification_reason = notify.reason

    return {
        "task_id": task.task_id,
        "status": task_status,
        "report_path": str(report_path),
        "notification_sent": notification_sent,
        "notification_reason": notification_reason,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_cli_args(argv)
    service = AnalysisService()
    notifier = FeishuNotifier(service.settings)
    symbols = _parse_symbols_csv(args.symbols)
    result = run_daily_analysis(
        service=service,
        notifier=notifier,
        force_run=bool(args.force_run),
        symbols=symbols,
        market=args.market,
        skip_notify=bool(args.skip_notify),
        output_dir=Path(args.output_dir),
        wait_timeout_seconds=int(args.wait_timeout_seconds),
        poll_interval_seconds=float(args.poll_interval_seconds),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return _exit_code_for_status(str(result["status"]))


def _exit_code_for_status(status: str) -> int:
    if status in {TaskStatus.COMPLETED.value, SKIPPED_STATUS}:
        return 0
    return 1


def _parse_symbols_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [s.strip().upper() for s in raw.split(",") if s.strip()]
    return values or None


def _resolve_symbols(
    *,
    configured_symbols: list[str],
    symbols: list[str] | None,
    market: str | None,
) -> list[str]:
    base = [s.upper() for s in (symbols or configured_symbols)]
    if market is None:
        return base
    prefix = market.upper() + ":"
    return [symbol for symbol in base if symbol.startswith(prefix)]


def _wait_task_completion(
    *,
    service: AnalysisService,
    task_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> AnalysisTask:
    deadline = time.monotonic() + max(1, timeout_seconds)
    fallback = service.get_task(task_id)
    while time.monotonic() <= deadline:
        task = service.get_task(task_id)
        if task is not None:
            fallback = task
            if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                return task
        if poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)
    if fallback is None:
        return AnalysisTask(
            task_id=task_id,
            status=TaskStatus.FAILED,
            symbols=[],
            force_refresh=False,
            error="Task lookup timeout",
        )
    return fallback


def _write_json_report(
    *,
    output_dir: Path,
    report_date: date,
    task_id: str,
    payload: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_etf_{report_date.isoformat()}_{task_id[:8]}.json"
    report_path = output_dir / filename
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report_path


def _build_markdown_summary(
    *,
    task_id: str,
    status: str,
    report_date: date,
    market: str,
    report_rows: list[dict[str, Any]],
    report_path: Path,
) -> str:
    top_lines = []
    for row in report_rows[:5]:
        symbol = row.get("symbol", "-")
        action = row.get("action", "-")
        score = row.get("score", "-")
        top_lines.append(f"{symbol}: action={action}, score={score}")
    details = "\n".join(top_lines) if top_lines else "No report rows found."
    return (
        f"Task: {task_id}\n"
        f"Status: {status}\n"
        f"Date: {report_date.isoformat()}\n"
        f"Market: {market}\n"
        f"Report: {report_path}\n"
        f"Top:\n{details}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
