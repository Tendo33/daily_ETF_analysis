from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from daily_etf_analysis.contracts.analysis_contracts import build_daily_report_contract
from daily_etf_analysis.domain import AnalysisTask, TaskStatus
from daily_etf_analysis.notifications import NotificationManager
from daily_etf_analysis.reports import render_daily_report_markdown
from daily_etf_analysis.services import AnalysisService, build_market_review

SKIPPED_STATUS = "skipped"


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily ETF analysis task")
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Skip trading-day guard and force refresh",
    )
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
    notifier: Any,
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
        markdown = _build_markdown_summary(
            task_id=SKIPPED_STATUS,
            status=SKIPPED_STATUS,
            report_date=report_date,
            market=report_market,
            report_rows=[],
        )
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
        markdown_path = _write_markdown_report(
            output_dir=output_dir,
            report_date=report_date,
            task_id=SKIPPED_STATUS,
            markdown=markdown,
        )
        return {
            "task_id": SKIPPED_STATUS,
            "task_ids": [],
            "status": SKIPPED_STATUS,
            "report_path": str(report_path),
            "markdown_report_path": str(markdown_path),
            "notification_sent": False,
            "notification_reason": "no_symbols_matched",
            "notification_channels": {},
        }

    run_id: str | None = None
    task_ids: list[str] = []
    if hasattr(service, "create_analysis_run") and hasattr(service, "repository"):
        try:
            run_window = _build_run_window(market=report_market)
            run = service.create_analysis_run(  # type: ignore[attr-defined]
                symbols=selected_symbols,
                markets=None if market is None else [market],
                force_refresh=force_run,
                force_retry=False,
                source="cli",
                run_window=run_window,
            )
            run_id = str(run.run_id)
            task_ids = _wait_for_run_task_ids(
                service=service,
                run_id=run_id,
                timeout_seconds=wait_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        except Exception:
            tasks = _submit_tasks(
                service=service,
                symbols=selected_symbols,
                force_run=force_run,
            )
            task_ids = [task.task_id for task in tasks]
    else:
        tasks = _submit_tasks(
            service=service,
            symbols=selected_symbols,
            force_run=force_run,
        )
        task_ids = [task.task_id for task in tasks]

    if not task_ids:
        tasks = _submit_tasks(
            service=service,
            symbols=selected_symbols,
            force_run=force_run,
        )
        task_ids = [task.task_id for task in tasks]

    final_tasks = _wait_tasks_completion(
        service=service,
        task_ids=task_ids,
        timeout_seconds=wait_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    task_status = _aggregate_task_status(final_tasks)

    report_date = (
        _resolve_report_date(service=service, task_ids=task_ids) or date.today()
    )
    report_rows = service.get_daily_report(report_date, market=report_market)
    history_by_symbol: dict[str, list[dict[str, Any]]] = {}
    if service.settings.report_history_compare_n > 0:
        history_by_symbol = service.get_recent_signals(
            symbols=selected_symbols,
            limit=service.settings.report_history_compare_n,
        )
    market_review = build_market_review(
        report_rows,
        industry_map=service.settings.industry_map,
        history_by_symbol=history_by_symbol,
        trend_window_days=service.settings.industry_trend_window_days,
        risk_top_n=service.settings.industry_risk_top_n,
        recommend_weights=service.settings.industry_recommend_weights,
    )
    failures = [
        {
            "task_id": task.task_id,
            "run_id": task.run_id,
            "symbols": task.symbols,
            "error_code": task.error_code.value,
            "error_message": task.error,
            "skip_reason": task.skip_reason,
        }
        for task in final_tasks
        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
    ]
    report_contract = build_daily_report_contract(
        target_date=report_date,
        market=report_market,
        report_rows=report_rows,
        run_id=run_id,
        failures=failures,
        run_summary_extra={
            "task_ids": task_ids,
            "status": task_status,
            "report_date": report_date.isoformat(),
        },
    )
    run_summary = report_contract["run_summary"]
    symbol_results = report_contract["symbol_results"]
    decision_quality = report_contract["decision_quality"]

    report_path = _write_json_report(
        output_dir=output_dir,
        report_date=report_date,
        task_id=task_ids[0],
        payload={
            "task_id": task_ids[0],
            "run_id": run_id,
            "task_ids": task_ids,
            "status": task_status,
            "report_date": report_date.isoformat(),
            "market": report_market,
            "symbols": selected_symbols,
            "report_rows": report_rows,
            "market_review": market_review,
            "history_by_symbol": history_by_symbol,
            "run_summary": run_summary,
            "symbol_results": symbol_results,
            "decision_quality": decision_quality,
            "failures": failures,
        },
    )
    markdown = _build_markdown_summary(
        task_id=task_ids[0],
        status=task_status,
        report_date=report_date,
        market=report_market,
        report_rows=report_rows,
        market_review=market_review,
        history_by_symbol=history_by_symbol,
    )
    markdown_path = _write_markdown_report(
        output_dir=output_dir,
        report_date=report_date,
        task_id=task_ids[0],
        markdown=markdown,
    )

    notification_sent = False
    notification_reason = "skipped" if skip_notify else "disabled"
    notification_channels: dict[str, dict[str, object]] = {}
    if not skip_notify:
        severity = _notification_severity(task_status=task_status, failures=failures)
        notify = notifier.send_markdown(
            title=f"[{severity}] daily_ETF_analysis",
            markdown=markdown,
        )
        notification_sent = notify.sent
        notification_reason = notify.reason
        channels = getattr(notify, "channel_results", None)
        if isinstance(channels, dict):
            for key, item in channels.items():
                sent_value = bool(getattr(item, "sent", False))
                reason_value = str(getattr(item, "reason", "unknown"))
                notification_channels[str(key)] = {
                    "sent": sent_value,
                    "reason": reason_value,
                }

    return {
        "task_id": task_ids[0],
        "run_id": run_id,
        "task_ids": task_ids,
        "status": task_status,
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
        "run_summary": run_summary,
        "symbol_results": symbol_results,
        "decision_quality": decision_quality,
        "failures": failures,
        "notification_sent": notification_sent,
        "notification_reason": notification_reason,
        "notification_channels": notification_channels,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_cli_args(argv)
    service = AnalysisService()
    notifier = NotificationManager(service.settings)
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
    deadline_monotonic: float | None = None,
) -> AnalysisTask:
    deadline = (
        deadline_monotonic
        if deadline_monotonic is not None
        else time.monotonic() + max(1, timeout_seconds)
    )
    fallback = service.get_task(task_id)
    while time.monotonic() <= deadline:
        task = service.get_task(task_id)
        if task is not None:
            fallback = task
            if task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
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


def _submit_tasks(
    *,
    service: AnalysisService,
    symbols: list[str],
    force_run: bool,
) -> list[AnalysisTask]:
    if hasattr(service, "run_analysis_batch"):
        tasks = service.run_analysis_batch(  # type: ignore[attr-defined]
            symbols=symbols,
            force_refresh=force_run,
            skip_market_guard=force_run,
        )
        if tasks:
            return tasks
    task = service.run_analysis(
        symbols=symbols,
        force_refresh=force_run,
        skip_market_guard=force_run,
    )
    return [task]


def _wait_tasks_completion(
    *,
    service: AnalysisService,
    task_ids: list[str],
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> list[AnalysisTask]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    return [
        _wait_task_completion(
            service=service,
            task_id=task_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            deadline_monotonic=deadline,
        )
        for task_id in task_ids
    ]


def _wait_for_run_task_ids(
    *,
    service: AnalysisService,
    run_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> list[str]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() <= deadline:
        tasks = []
        if hasattr(service, "repository"):
            tasks = service.repository.list_tasks_by_run(run_id)  # type: ignore[attr-defined]
        if tasks:
            return [task.task_id for task in tasks]
        if poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)
    return []


def _aggregate_task_status(tasks: list[AnalysisTask]) -> str:
    for task in tasks:
        if task.status == TaskStatus.FAILED:
            return TaskStatus.FAILED.value
    has_cancelled = any(task.status == TaskStatus.CANCELLED for task in tasks)
    for task in tasks:
        if task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return TaskStatus.FAILED.value
    if has_cancelled:
        return TaskStatus.CANCELLED.value
    return TaskStatus.COMPLETED.value


def _resolve_report_date(service: AnalysisService, task_ids: list[str]) -> date | None:
    latest: date | None = None
    for task_id in task_ids:
        value = service.get_task_report_date(task_id)
        if value is None:
            continue
        if latest is None or value > latest:
            latest = value
    return latest


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
    notes: str | None = None,
    skip_reason: str | None = None,
    market_review: dict[str, Any] | None = None,
    history_by_symbol: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    return render_daily_report_markdown(
        task_id=task_id,
        status=status,
        report_date=report_date,
        market=market,
        report_rows=report_rows,
        disclaimer="For research only; not investment advice.",
        notes=notes,
        skip_reason=skip_reason,
        market_review=market_review,
        history_by_symbol=history_by_symbol,
    )


def _write_markdown_report(
    *, output_dir: Path, report_date: date, task_id: str, markdown: str
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_filename = f"report_{report_date.strftime('%Y%m%d')}_{task_id[:8]}.md"
    report_path = output_dir / run_filename
    report_path.write_text(markdown, encoding="utf-8")

    legacy_path = output_dir / f"report_{report_date.strftime('%Y%m%d')}.md"
    legacy_path.write_text(markdown, encoding="utf-8")
    return report_path


def _notification_severity(*, task_status: str, failures: list[dict[str, Any]]) -> str:
    if task_status == TaskStatus.COMPLETED.value and not failures:
        return "OK"
    if failures and task_status in {
        TaskStatus.COMPLETED.value,
        TaskStatus.CANCELLED.value,
    }:
        return "WARN"
    return "ALERT"


def _build_run_window(*, market: str) -> str:
    today = date.today().isoformat()
    return f"{market}:{today}"


if __name__ == "__main__":
    raise SystemExit(main())
