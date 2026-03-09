from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.services.analysis_service import AnalysisService


class EtfScheduler:
    def __init__(
        self, service: AnalysisService, settings: Settings | None = None
    ) -> None:
        self.service = service
        self.settings = settings or get_settings()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_marker: set[str] = set()

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
        self._maybe_run("cn", self.settings.schedule_cron_cn, now_cn)
        self._maybe_run("hk", self.settings.schedule_cron_hk, now_hk)
        self._maybe_run("us", self.settings.schedule_cron_us, now_us)

    def _maybe_run(self, market: str, cron_expr: str, now: datetime) -> None:
        if not _matches_simple_cron(cron_expr, now):
            return
        marker = f"{market}:{now.strftime('%Y%m%d%H%M')}"
        if marker in self._last_run_marker:
            return
        symbols = [
            s for s in self.settings.etf_list if s.startswith(market.upper() + ":")
        ]
        if symbols:
            self.service.run_analysis(symbols=symbols, force_refresh=False)
        self._last_run_marker.add(marker)


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
