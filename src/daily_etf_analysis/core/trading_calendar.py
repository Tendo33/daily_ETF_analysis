from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from daily_etf_analysis.domain import Market, split_symbol

_MARKET_EXCHANGE = {Market.CN: "XSHG", Market.HK: "XHKG", Market.US: "XNYS"}
_MARKET_TZ = {
    Market.CN: "Asia/Shanghai",
    Market.HK: "Asia/Hong_Kong",
    Market.US: "America/New_York",
}

try:
    import exchange_calendars as xcals

    _HAS_CALENDAR = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_CALENDAR = False


def market_for_symbol(symbol: str) -> Market:
    market, _ = split_symbol(symbol)
    return market


def is_market_open_today(market: Market) -> bool:
    if market == Market.INDEX:
        return True
    if not _HAS_CALENDAR:
        return True
    tz = ZoneInfo(_MARKET_TZ[market])
    today = datetime.now(tz).date()
    calendar = xcals.get_calendar(_MARKET_EXCHANGE[market])
    return calendar.is_session(datetime(today.year, today.month, today.day))
