from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.trading_calendar import is_market_open_today
from daily_etf_analysis.domain import Market
from daily_etf_analysis.observability.metrics import inc_scheduler_run
from daily_etf_analysis.services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)


class EtfScheduler:
    def __init__(
        self,
        service: AnalysisService,
        settings: Settings | None = None,
        on_run: Callable[[str, list[str]], None] | None = None,
    ) -> None:
        self.service = service
        self.settings = settings or get_settings()
        self._on_run = on_run
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_marker: set[str] = set()
        self._last_next_run_log_marker: str | None = None

    def start(self) -> None:
        if not self.settings.schedule_enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="etf-scheduler"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            time.sleep(30)

    def _tick(self) -> None:
        now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
        now_hk = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        now_us = datetime.now(ZoneInfo("America/New_York"))
        self._log_next_runs(now_cn=now_cn, now_hk=now_hk, now_us=now_us)
        self._maybe_run("cn", self.settings.schedule_cron_cn, now_cn)
        self._maybe_run("hk", self.settings.schedule_cron_hk, now_hk)
        self._maybe_run("us", self.settings.schedule_cron_us, now_us)

    def _maybe_run(self, market: str, cron_expr: str, now: datetime) -> None:
        if market.lower() not in {m.lower() for m in self.settings.markets_enabled}:
            return
        if not _matches_simple_cron(cron_expr, now):
            return
        market_enum = Market[market.upper()]
        if not is_market_open_today(market_enum):
            inc_scheduler_run(market, "skipped")
            return
        if not _is_after_market_close(market, now):
            inc_scheduler_run(market, "skipped")
            return
        marker = f"{market}:{now.strftime('%Y%m%d%H%M')}"
        if marker in self._last_run_marker:
            return
        symbols = [
            s for s in self.settings.etf_list if s.startswith(market.upper() + ":")
        ]
        if symbols:
            if self._on_run is not None:
                try:
                    self._on_run(market, symbols)
                    inc_scheduler_run(market, "success")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Scheduler callback failed: %s", exc)
                    inc_scheduler_run(market, "failed")
            else:
                if hasattr(self.service, "run_analysis_batch"):
                    self.service.run_analysis_batch(  # type: ignore[attr-defined]
                        symbols=symbols,
                        force_refresh=False,
                    )
                else:
                    self.service.run_analysis(symbols=symbols, force_refresh=False)
                inc_scheduler_run(market, "success")
            logger.info("Scheduler triggered market=%s symbols=%s", market, symbols)
        else:
            inc_scheduler_run(market, "skipped")
        self._last_run_marker.add(marker)

    def _log_next_runs(
        self, *, now_cn: datetime, now_hk: datetime, now_us: datetime
    ) -> None:
        log_marker = now_cn.strftime("%Y%m%d%H%M")
        if self._last_next_run_log_marker == log_marker:
            return
        self._last_next_run_log_marker = log_marker

        contexts = (
            ("cn", self.settings.schedule_cron_cn, now_cn),
            ("hk", self.settings.schedule_cron_hk, now_hk),
            ("us", self.settings.schedule_cron_us, now_us),
        )
        enabled = {m.lower() for m in self.settings.markets_enabled}
        for market, cron_expr, now in contexts:
            if market not in enabled:
                continue
            next_run = next_run_for_cron(cron_expr, now)
            logger.info(
                "Scheduler next run market=%s local_now=%s next_run=%s",
                market,
                now.isoformat(),
                next_run.isoformat() if next_run else "unavailable",
            )


def _matches_simple_cron(cron_expr: str, now: datetime) -> bool:
    parts = cron_expr.split()
    if len(parts) != 6:
        return False
    sec, minute, hour, _day, _month, weekday = parts
    if not (_match_int_field(sec, now.second) and _match_int_field(minute, now.minute)):
        return False
    if not _match_int_field(hour, now.hour):
        return False
    return _match_weekday(weekday, now.isoweekday())


def _match_int_field(field: str, value: int) -> bool:
    if field == "*":
        return True
    if "-" in field:
        start, end = field.split("-", 1)
        return int(start) <= value <= int(end)
    return int(field) == value


def _match_weekday(field: str, iso_weekday: int) -> bool:
    if field == "*":
        return True
    # cron-style weekday in our config: 1-5 (Mon-Fri)
    return _match_int_field(field, iso_weekday)


def _field_values(field: str, *, min_value: int, max_value: int) -> list[int]:
    if field == "*":
        return list(range(min_value, max_value + 1))
    if "-" in field:
        start, end = field.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(field)]


def next_run_for_cron(cron_expr: str, now: datetime) -> datetime | None:
    parts = cron_expr.split()
    if len(parts) != 6:
        return None
    sec, minute, hour, _day, _month, weekday = parts
    seconds = _field_values(sec, min_value=0, max_value=59)
    minutes = _field_values(minute, min_value=0, max_value=59)
    hours = _field_values(hour, min_value=0, max_value=23)

    for day_offset in range(0, 15):
        current = now + timedelta(days=day_offset)
        day = current.date()
        iso_weekday = current.isoweekday()
        if not _match_weekday(weekday, iso_weekday):
            continue
        for h in hours:
            for m in minutes:
                for s in seconds:
                    candidate = datetime(
                        year=day.year,
                        month=day.month,
                        day=day.day,
                        hour=h,
                        minute=m,
                        second=s,
                        tzinfo=now.tzinfo,
                    )
                    if candidate > now:
                        return candidate
    return None


def _is_after_market_close(market: str, now: datetime) -> bool:
    close_by_market = {
        "cn": (15, 0),
        "hk": (16, 10),
        "us": (16, 0),
    }
    market_key = market.lower()
    if market_key not in close_by_market:
        return True
    close_hour, close_minute = close_by_market[market_key]
    close_time = now.replace(
        hour=close_hour, minute=close_minute, second=0, microsecond=0
    )
    return now >= close_time
