"""Minimal tests for settings behavior."""

from __future__ import annotations

from pathlib import Path

from python_template.config.settings import get_settings, reload_settings


def test_get_settings_returns_cached_instance() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_reload_settings_reads_custom_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "ENVIRONMENT=production\nLOG_LEVEL=debug\n",
        encoding="utf-8",
    )

    settings = reload_settings(env_file=env_file)
    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"

    get_settings.cache_clear()
