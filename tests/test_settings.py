"""Minimal tests for settings behavior."""

from __future__ import annotations

from pathlib import Path

from daily_etf_analysis.config.settings import Settings, get_settings, reload_settings


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


def test_default_realtime_source_priority_is_phase2_chain(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("REALTIME_SOURCE_PRIORITY", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.realtime_source_priority == [
        "efinance",
        "akshare",
        "tushare",
        "pytdx",
        "baostock",
        "yfinance",
    ]


def test_csv_env_lists_parse_without_json_decode(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ETF_LIST", "CN:159659,US:QQQ,HK:02800")
    monkeypatch.setenv("MARKETS_ENABLED", "cn,hk,us")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.etf_list == ["CN:159659", "US:QQQ", "HK:02800"]
    assert settings.markets_enabled == ["cn", "hk", "us"]


def test_json_env_list_still_supported(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ETF_LIST", '["CN:159659","US:QQQ"]')

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.etf_list == ["CN:159659", "US:QQQ"]


def test_report_type_alias(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REPORT_TYPE", "brief")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.report_type == "brief"


def test_theme_intel_enabled_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("THEME_INTEL_ENABLED", "false")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.theme_intel_enabled is False


def test_etf_theme_map_parsing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(
        "ETF_THEME_MAP",
        '{"CN:159392":["航空航天","低空经济"],"US:QQQ":["纳斯达克"]}',
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.etf_theme_map["CN:159392"] == ["航空航天", "低空经济"]
    assert settings.etf_theme_map["US:QQQ"] == ["纳斯达克"]
