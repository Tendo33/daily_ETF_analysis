from __future__ import annotations

import re

from daily_etf_analysis.domain.enums import Market

_US_TICKER_PATTERN = re.compile(r"^[A-Z]{1,10}(\.[A-Z])?$")


def infer_market(code: str) -> Market:
    c = code.strip().upper()
    if c in {"SPX", "NDX", "DJI", "IXIC", "HSI", "HSCEI"}:
        return Market.INDEX
    if c.isdigit() and len(c) == 6:
        return Market.CN
    if c.isdigit() and len(c) == 5:
        return Market.HK
    if _US_TICKER_PATTERN.match(c):
        return Market.US
    raise ValueError(f"Unable to infer market from code: {code}")


def normalize_symbol(symbol: str) -> str:
    raw = symbol.strip().upper()
    if ":" in raw:
        market, code = raw.split(":", 1)
        market_enum = Market(market)
        return f"{market_enum.value}:{code}"
    market_enum = infer_market(raw)
    return f"{market_enum.value}:{raw}"


def split_symbol(symbol: str) -> tuple[Market, str]:
    normalized = normalize_symbol(symbol)
    market_str, code = normalized.split(":", 1)
    return Market(market_str), code
