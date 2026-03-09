from __future__ import annotations

from pathlib import Path

from daily_etf_analysis.config.settings import reload_settings


def test_channels_override_legacy(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("LLM_CHANNELS", "aihubmix")
    monkeypatch.setenv("LLM_AIHUBMIX_API_KEY", "test-key-123456")
    monkeypatch.setenv("LLM_AIHUBMIX_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setenv("LLM_AIHUBMIX_MODELS", "gpt-4o-mini")
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-key-123456")

    settings = reload_settings()
    assert settings.llm_model_list
    assert settings.llm_model_list[0]["litellm_params"]["model"] == "openai/gpt-4o-mini"
    assert settings.litellm_model == "openai/gpt-4o-mini"


def test_yaml_override_channels(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    yaml_file = tmp_path / "litellm_config.yaml"
    yaml_file.write_text(
        """
model_list:
  - model_name: openai/gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: "os.environ/OPENAI_API_KEY"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-123456")
    monkeypatch.setenv("LITELLM_CONFIG", str(yaml_file))
    monkeypatch.setenv("LLM_CHANNELS", "aihubmix")
    monkeypatch.setenv("LLM_AIHUBMIX_API_KEY", "channel-key-123456")
    monkeypatch.setenv("LLM_AIHUBMIX_MODELS", "gpt-4o-mini")

    settings = reload_settings()
    assert settings.llm_model_list
    assert (
        settings.llm_model_list[0]["litellm_params"]["api_key"] == "openai-key-123456"
    )
