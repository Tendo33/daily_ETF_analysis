from __future__ import annotations

import argparse
import threading
import time
from datetime import date
from pathlib import Path

import uvicorn

from daily_etf_analysis.cli.run_daily_analysis import run_daily_analysis
from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.core.trading_calendar import is_market_open_today
from daily_etf_analysis.domain import Market
from daily_etf_analysis.notifications import NotificationManager
from daily_etf_analysis.observability.log_config import get_default_logger
from daily_etf_analysis.reports import render_daily_report_markdown
from daily_etf_analysis.scheduler import EtfScheduler
from daily_etf_analysis.services import AnalysisService, build_market_review

logger = get_default_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="daily_ETF_analysis entrypoint")
    parser.add_argument("--schedule", action="store_true", help="Enable scheduler")
    parser.add_argument("--serve", action="store_true", help="Run API server")
    parser.add_argument("--serve-only", action="store_true", help="Run API server only")
    parser.add_argument(
        "--market-review",
        action="store_true",
        help="Run market review only",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip notifications",
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Skip trading day guard",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    return parser.parse_args()


def _resolve_symbols(settings, market: str | None) -> list[str]:
    symbols = settings.etf_list
    if not market:
        return symbols
    prefix = market.upper() + ":"
    return [s for s in symbols if s.startswith(prefix)]


def _send_skip_notification(
    *, notifier: NotificationManager, market: str, reason: str
) -> None:
    markdown = render_daily_report_markdown(
        task_id="skipped",
        status="skipped",
        report_date=date.today(),
        market=market,
        report_rows=[],
        disclaimer="For research only; not investment advice.",
        skip_reason=reason,
    )
    result = notifier.send_markdown(title="daily_ETF_analysis", markdown=markdown)
    logger.info(f"Skip notification sent={result.sent} reason={result.reason}")


def _run_market_review(
    *,
    service: AnalysisService,
    notifier: NotificationManager,
    market: str,
    skip_notify: bool,
) -> None:
    report_date = date.today()
    report_rows = service.get_daily_report(report_date, market=market)
    history_by_symbol = {}
    if service.settings.report_history_compare_n > 0:
        history_by_symbol = service.get_recent_signals(
            symbols=_resolve_symbols(service.settings, market),
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
    markdown = render_daily_report_markdown(
        task_id="market-review",
        status="completed" if report_rows else "skipped",
        report_date=report_date,
        market=market,
        report_rows=report_rows,
        disclaimer="For research only; not investment advice.",
        market_review=market_review,
        history_by_symbol=history_by_symbol,
        notes="No report rows available" if not report_rows else None,
    )
    if skip_notify:
        logger.info("Market review generated but notifications are disabled")
        return
    notifier.send_markdown(title="daily_ETF_analysis", markdown=markdown)


def _start_api(host: str, port: int) -> None:
    uvicorn.run(
        "daily_etf_analysis.api.app:app",
        host=host,
        port=port,
        log_level="info",
    )


def main() -> int:
    args = parse_args()
    settings = get_settings()
    service = AnalysisService(settings)
    notifier = NotificationManager(settings)

    if args.market_review:
        _run_market_review(
            service=service,
            notifier=notifier,
            market="cn",
            skip_notify=bool(args.no_notify),
        )
        return 0

    scheduler_enabled = args.schedule or settings.schedule_enabled
    if scheduler_enabled:

        def scheduled_task(market: str, symbols: list[str]) -> None:
            market_key = market.lower()
            if not args.force_run:
                try:
                    market_enum = Market[market_key.upper()]
                except KeyError:
                    market_enum = None
                if market_enum in {
                    Market.CN,
                    Market.HK,
                    Market.US,
                } and not is_market_open_today(market_enum):
                    _send_skip_notification(
                        notifier=notifier,
                        market=market_key,
                        reason="Market closed today; analysis skipped.",
                    )
                    return
            run_daily_analysis(
                service=service,
                notifier=notifier,
                force_run=bool(args.force_run),
                symbols=symbols,
                market=market_key,
                skip_notify=bool(args.no_notify),
                output_dir=Path("reports"),
                wait_timeout_seconds=900,
                poll_interval_seconds=2.0,
            )

        scheduler = EtfScheduler(
            service=service, settings=settings, on_run=scheduled_task
        )
        scheduler.start()
        logger.info("Scheduler started")

    if args.serve or args.serve_only:
        if scheduler_enabled:
            api_thread = threading.Thread(
                target=_start_api,
                kwargs={"host": args.host, "port": args.port},
                daemon=True,
            )
            api_thread.start()
            logger.info("API server started in background")
        else:
            _start_api(args.host, args.port)
            return 0

    if scheduler_enabled:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping scheduler...")
            scheduler.stop()
        return 0

    if not args.serve_only:
        run_daily_analysis(
            service=service,
            notifier=notifier,
            force_run=bool(args.force_run),
            symbols=_resolve_symbols(settings, "cn"),
            market="cn",
            skip_notify=bool(args.no_notify),
            output_dir=Path("reports"),
            wait_timeout_seconds=900,
            poll_interval_seconds=2.0,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
