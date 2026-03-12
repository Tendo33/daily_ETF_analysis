"""Contracts package public API."""

from .analysis_contracts import (
    build_daily_report_contract,
    build_run_detail_contract,
)
from .protocols import (
    AsyncCloseable,
    AsyncFileReader,
    AsyncFileWriter,
    Closeable,
    Configurable,
    FileReader,
    FileWriter,
    Serializable,
)

__all__ = [
    "Serializable",
    "FileReader",
    "AsyncFileReader",
    "FileWriter",
    "AsyncFileWriter",
    "Closeable",
    "AsyncCloseable",
    "Configurable",
    "build_daily_report_contract",
    "build_run_detail_contract",
]
