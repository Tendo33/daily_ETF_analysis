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
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskErrorCode(str, Enum):
    NONE = "NONE"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    TASK_EXEC_FAILED = "TASK_EXEC_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    LLM_FAILED = "LLM_FAILED"
    UNKNOWN = "UNKNOWN"


_LEGACY_TASK_STATUS_MAP = {
    "queued": TaskStatus.PENDING,
    "running": TaskStatus.PROCESSING,
    "skipped": TaskStatus.COMPLETED,
}


def parse_task_status(value: str) -> TaskStatus:
    normalized = value.strip().lower()
    if normalized in _LEGACY_TASK_STATUS_MAP:
        return _LEGACY_TASK_STATUS_MAP[normalized]
    return TaskStatus(normalized)
