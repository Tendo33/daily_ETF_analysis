"""Import smoke tests for public SDK APIs."""

import importlib


def test_canonical_imports() -> None:
    from daily_etf_analysis.config.settings import get_settings
    from daily_etf_analysis.observability.log_config import get_logger, setup_logging
    from daily_etf_analysis.utils import (
        read_json,
        read_text_file,
        write_json,
        write_text_file,
    )

    assert callable(get_settings)
    assert callable(get_logger)
    assert callable(setup_logging)
    assert callable(read_json)
    assert callable(write_json)
    assert callable(read_text_file)
    assert callable(write_text_file)


def test_advanced_imports() -> None:
    from daily_etf_analysis.core.context import Context
    from daily_etf_analysis.utils.common_utils import chunk_list
    from daily_etf_analysis.utils.decorator_utils import retry_decorator

    assert Context is not None
    assert callable(chunk_list)
    assert callable(retry_decorator)


def test_public_modules_importable() -> None:
    modules = [
        "daily_etf_analysis",
        "daily_etf_analysis.config",
        "daily_etf_analysis.config.settings",
        "daily_etf_analysis.observability",
        "daily_etf_analysis.observability.log_config",
        "daily_etf_analysis.utils",
        "daily_etf_analysis.utils.file_utils",
        "daily_etf_analysis.utils.json_utils",
        "daily_etf_analysis.utils.date_utils",
        "daily_etf_analysis.utils.common_utils",
        "daily_etf_analysis.utils.decorator_utils",
        "daily_etf_analysis.core",
        "daily_etf_analysis.core.context",
        "daily_etf_analysis.contracts",
        "daily_etf_analysis.contracts.protocols",
        "daily_etf_analysis.models",
        "daily_etf_analysis.models.base",
        "daily_etf_analysis.models.examples",
    ]

    for module in modules:
        assert importlib.import_module(module) is not None
