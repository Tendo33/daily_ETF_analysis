from __future__ import annotations

from daily_etf_analysis.config.settings import reload_settings


def test_openai_key_normalization(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key-123456")
    settings = reload_settings()
    assert settings.openai_api_keys == ["legacy-key-123456"]
    assert settings.openai_model == "gpt-4o-mini"


def test_openai_model_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key-123456")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    settings = reload_settings()
    assert settings.openai_model == "gpt-4o"
