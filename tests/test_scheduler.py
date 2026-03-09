from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.scheduler.scheduler import EtfScheduler, next_run_for_cron


class _SpyService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run_analysis(self, symbols, force_refresh=False):  # type: ignore[no-untyped-def]
        self.calls.append(list(symbols))
        return None


def test_scheduler_respects_markets_enabled() -> None:
    settings = Settings(
        schedule_enabled=True,
        markets_enabled=["cn"],
        etf_list=["CN:159659", "US:QQQ"],
        schedule_cron_cn="0 0 9 * * 1-5",
        schedule_cron_us="0 0 9 * * 1-5",
    )
    service = _SpyService()
    scheduler = EtfScheduler(service=service, settings=settings)
    now = datetime(2026, 3, 9, 9, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scheduler._maybe_run("cn", settings.schedule_cron_cn, now)
    scheduler._maybe_run("us", settings.schedule_cron_us, now)

    assert service.calls == [["CN:159659"]]


def test_scheduler_deduplicates_same_minute() -> None:
    settings = Settings(
        schedule_enabled=True,
        markets_enabled=["cn"],
        etf_list=["CN:159659"],
        schedule_cron_cn="0 0 9 * * 1-5",
    )
    service = _SpyService()
    scheduler = EtfScheduler(service=service, settings=settings)
    now = datetime(2026, 3, 9, 9, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scheduler._maybe_run("cn", settings.schedule_cron_cn, now)
    scheduler._maybe_run("cn", settings.schedule_cron_cn, now)

    assert len(service.calls) == 1


def test_next_run_for_cron_weekday() -> None:
    tz = ZoneInfo("Asia/Shanghai")
    cron_expr = "0 0 21 * * 1-5"

    before_run = datetime(2026, 3, 9, 20, 30, 0, tzinfo=tz)
    first = next_run_for_cron(cron_expr, before_run)
    assert first == datetime(2026, 3, 9, 21, 0, 0, tzinfo=tz)

    after_run = datetime(2026, 3, 9, 21, 0, 30, tzinfo=tz)
    second = next_run_for_cron(cron_expr, after_run)
    assert second == datetime(2026, 3, 10, 21, 0, 0, tzinfo=tz)
