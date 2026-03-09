"""Import smoke tests for public SDK APIs."""

import importlib


def test_canonical_imports() -> None:
    from python_template.config.settings import get_settings
    from python_template.observability.log_config import get_logger, setup_logging
    from python_template.utils import (
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
    from python_template.core.context import Context
    from python_template.utils.common_utils import chunk_list
    from python_template.utils.decorator_utils import retry_decorator

    assert Context is not None
    assert callable(chunk_list)
    assert callable(retry_decorator)


def test_public_modules_importable() -> None:
    modules = [
        "python_template",
        "python_template.config",
        "python_template.config.settings",
        "python_template.observability",
        "python_template.observability.log_config",
        "python_template.utils",
        "python_template.utils.file_utils",
        "python_template.utils.json_utils",
        "python_template.utils.date_utils",
        "python_template.utils.common_utils",
        "python_template.utils.decorator_utils",
        "python_template.core",
        "python_template.core.context",
        "python_template.contracts",
        "python_template.contracts.protocols",
        "python_template.models",
        "python_template.models.base",
        "python_template.models.examples",
    ]

    for module in modules:
        assert importlib.import_module(module) is not None
