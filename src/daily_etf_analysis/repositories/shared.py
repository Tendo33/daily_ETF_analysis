from __future__ import annotations

from daily_etf_analysis.domain import TaskErrorCode


def float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_task_error_code(value: str | None) -> TaskErrorCode:
    if not value:
        return TaskErrorCode.NONE
    try:
        return TaskErrorCode(value)
    except ValueError:
        return TaskErrorCode.UNKNOWN
