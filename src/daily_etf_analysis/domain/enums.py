from __future__ import annotations

from enum import Enum


class Market(str, Enum):
    CN = "CN"
    HK = "HK"
    US = "US"
    INDEX = "INDEX"


class Trend(str, Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class Action(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
