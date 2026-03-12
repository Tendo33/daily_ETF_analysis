from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from daily_etf_analysis.cli.run_daily_analysis import run_daily_analysis
from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.core.trading_calendar import is_market_open_today
from daily_etf_analysis.domain import Market
from daily_etf_analysis.notifications import NotificationManager
from daily_etf_analysis.observability.log_config import get_default_logger
from daily_etf_analysis.reports import render_daily_report_markdown
from daily_etf_analysis.scheduler import EtfScheduler
from daily_etf_analysis.services import AnalysisService

logger = get_default_logger()


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


def main() -> int:
    settings = get_settings()
    if not settings.schedule_enabled:
        logger.warning("Scheduler disabled (SCHEDULE_ENABLED=false). Exiting.")
        return 1

    service = AnalysisService(settings)
    notifier = NotificationManager(settings)

    def scheduled_task(market: str, symbols: list[str]) -> None:
        if market.lower() != "cn":
            logger.info(f"Skipping market={market} (only cn is enabled in scheduler).")
            return
        if not is_market_open_today(Market.CN):
            _send_skip_notification(
                notifier=notifier,
                market=market,
                reason="Market closed today; analysis skipped.",
            )
            return

        run_daily_analysis(
            service=service,
            notifier=notifier,
            force_run=False,
            symbols=symbols,
            market=market,
            skip_notify=False,
            output_dir=Path("reports"),
            wait_timeout_seconds=900,
            poll_interval_seconds=2.0,
        )

    scheduler = EtfScheduler(service=service, settings=settings, on_run=scheduled_task)
    started = scheduler.start()
    if not started:
        logger.warning("Scheduler not started.")
        return 1

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping scheduler...")
        scheduler.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
