from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from daily_etf_analysis.config.settings import Settings, reload_settings
from daily_etf_analysis.repositories import EtfRepository


class SystemConfigService:
    UPDATABLE_FIELDS = {
        "etf_list",
        "index_proxy_map",
        "markets_enabled",
        "news_max_age_days",
        "news_provider_priority",
        "realtime_source_priority",
        "provider_max_retries",
        "provider_backoff_ms",
        "provider_circuit_fail_threshold",
        "provider_circuit_reset_seconds",
        "notify_channels",
        "schedule_enabled",
        "schedule_cron_cn",
        "schedule_cron_hk",
        "schedule_cron_us",
    }

    def __init__(self, settings: Settings, repository: EtfRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.on_settings_applied: Callable[[Settings], None] | None = None

    def set_on_settings_applied(
        self, callback: Callable[[Settings], None] | None
    ) -> None:
        self.on_settings_applied = callback

    def get_system_config(self) -> dict[str, Any]:
        latest = self.repository.get_latest_system_config_snapshot()
        if latest is not None:
            return {"version": latest["version"], "config": latest["config"]}
        return {"version": 0, "config": self._current_config_payload()}

    def validate_system_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        unknown_fields = sorted(set(updates.keys()) - self.UPDATABLE_FIELDS)
        if unknown_fields:
            for field in unknown_fields:
                issues.append(
                    {
                        "severity": "error",
                        "field": field,
                        "message": f"Field is not updatable: {field}",
                    }
                )

        candidate = self._baseline_config_payload()
        for key, value in updates.items():
            if key in self.UPDATABLE_FIELDS:
                candidate[key] = value

        model_payload = self.settings.model_dump()
        model_payload.update(candidate)
        try:
            Settings.model_validate(model_payload)
        except ValidationError as exc:
            for item in exc.errors():
                issues.append(
                    {
                        "severity": "error",
                        "field": ".".join(str(v) for v in item.get("loc", [])),
                        "message": str(item.get("msg", "validation error")),
                    }
                )

        return {
            "valid": not any(issue["severity"] == "error" for issue in issues),
            "issues": issues,
            "candidate_config": candidate,
        }

    def update_system_config(
        self, expected_version: int, updates: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        validation = self.validate_system_config(updates)
        if not validation["valid"]:
            raise ValueError("invalid_config")

        version = self.repository.create_system_config_snapshot(
            config_payload=validation["candidate_config"],
            actor=actor,
            expected_version=expected_version,
        )
        self.repository.create_system_config_audit_log(
            version=version,
            actor=actor,
            action="update",
            changes=updates,
        )

        previous_settings = self.settings
        try:
            reloaded = reload_settings()
            merged_payload = reloaded.model_dump()
            merged_payload.update(validation["candidate_config"])
            runtime_settings = Settings.model_validate(merged_payload)
            self.settings = runtime_settings
            if self.on_settings_applied is not None:
                self.on_settings_applied(runtime_settings)
        except Exception as exc:  # noqa: BLE001
            self.settings = previous_settings
            self.repository.delete_system_config_snapshot(version)
            self.repository.create_system_config_audit_log(
                version=expected_version,
                actor=actor,
                action="rollback",
                changes={"reason": f"reload_failed: {exc}"},
            )
            raise ValueError(f"reload_failed: {exc}") from exc

        latest = self.repository.get_latest_system_config_snapshot()
        if latest is None:
            return {"version": 0, "config": self._current_config_payload()}
        return {"version": latest["version"], "config": latest["config"]}

    def get_system_config_schema(self) -> dict[str, Any]:
        fields: dict[str, dict[str, Any]] = {}
        for field in sorted(self.UPDATABLE_FIELDS):
            model_field = Settings.model_fields.get(field)
            if model_field is None:
                continue
            annotation = model_field.annotation
            fields[field] = {
                "type": str(annotation),
                "required": model_field.is_required(),
            }
        return {"fields": fields}

    def list_system_config_audit(
        self, page: int = 1, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self.repository.list_system_config_audit_logs(page=page, limit=limit)

    def _current_config_payload(self) -> dict[str, Any]:
        return self._settings_payload(self.settings)

    def _baseline_config_payload(self) -> dict[str, Any]:
        latest = self.repository.get_latest_system_config_snapshot()
        if latest is None:
            return self._current_config_payload()

        raw_config = latest.get("config")
        if not isinstance(raw_config, dict):
            return self._current_config_payload()

        baseline = self._current_config_payload()
        for field in self.UPDATABLE_FIELDS:
            if field in raw_config:
                baseline[field] = raw_config[field]
        return baseline

    def _settings_payload(self, settings: Settings) -> dict[str, Any]:
        dumped = settings.model_dump()
        return {key: dumped.get(key) for key in self.UPDATABLE_FIELDS if key in dumped}
