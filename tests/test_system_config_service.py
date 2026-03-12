from __future__ import annotations

from pathlib import Path

from daily_etf_analysis.api.runtime import AppRuntime
from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.repositories.repository import EtfRepository
from daily_etf_analysis.services.system_config_service import SystemConfigService


def _build_settings(db_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{db_path}",
        etf_list=["US:QQQ"],
        index_proxy_map={"NDX": ["US:QQQ"]},
    )


def test_validate_uses_latest_snapshot_as_baseline(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path / "baseline.db")
    repository = EtfRepository(settings)
    service = SystemConfigService(settings=settings, repository=repository)

    version = repository.create_system_config_snapshot(
        config_payload={"etf_list": ["CN:159659"]},
        actor="admin",
        expected_version=0,
    )
    assert version == 1

    validated = service.validate_system_config({"news_max_age_days": 9})
    assert validated["valid"] is True
    assert validated["candidate_config"]["etf_list"] == ["CN:159659"]
    assert validated["candidate_config"]["news_max_age_days"] == 9


def test_system_config_updates_are_composable_even_with_stale_runtime_settings(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    settings = _build_settings(tmp_path / "compose.db")
    repository = EtfRepository(settings)
    service = SystemConfigService(settings=settings, repository=repository)
    monkeypatch.setattr(
        "daily_etf_analysis.services.system_config_service.reload_settings",
        lambda: settings,
    )

    first = service.update_system_config(
        expected_version=0,
        updates={"etf_list": ["CN:159659"]},
        actor="admin",
    )
    assert first["config"]["etf_list"] == ["CN:159659"]

    # Simulate stale in-memory settings and ensure second update still uses snapshot.
    service.settings = _build_settings(tmp_path / "compose.db")
    second = service.update_system_config(
        expected_version=1,
        updates={"news_max_age_days": 9},
        actor="admin",
    )
    assert second["config"]["etf_list"] == ["CN:159659"]
    assert second["config"]["news_max_age_days"] == 9


def test_runtime_applies_updated_settings_and_swaps_service(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    settings = _build_settings(tmp_path / "analysis.db")
    runtime = AppRuntime(settings=settings)
    service = runtime.get_service()

    monkeypatch.setattr(
        "daily_etf_analysis.services.system_config_service.reload_settings",
        lambda: settings,
    )

    payload = service.update_system_config(
        expected_version=0,
        updates={"etf_list": ["CN:159659"], "index_proxy_map": {"HSI": ["CN:159920"]}},
        actor="admin",
    )

    assert payload["config"]["etf_list"] == ["CN:159659"]
    new_service = runtime.get_service()
    assert new_service is not service
    assert new_service.settings.etf_list == ["CN:159659"]
    runtime.shutdown()


def test_runtime_shuts_down_old_task_manager_on_reload(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    settings = _build_settings(tmp_path / "analysis-reload.db")
    runtime = AppRuntime(settings=settings)
    service = runtime.get_service()
    old_manager = service.task_manager
    shutdown_calls = {"count": 0}
    original_shutdown = old_manager.shutdown

    def _counted_shutdown() -> None:
        shutdown_calls["count"] += 1
        original_shutdown()

    monkeypatch.setattr(old_manager, "shutdown", _counted_shutdown)
    monkeypatch.setattr(
        "daily_etf_analysis.services.system_config_service.reload_settings",
        lambda: settings,
    )

    _ = service.update_system_config(
        expected_version=0,
        updates={"etf_list": ["CN:159659"]},
        actor="admin",
    )

    assert shutdown_calls["count"] == 1
    assert runtime.get_service().task_manager is not old_manager
    runtime.shutdown()
