from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class BacktestSignal:
    symbol: str
    trade_date: date
    action: str


@dataclass(slots=True)
class BacktestPricePoint:
    symbol: str
    trade_date: date
    close: float
