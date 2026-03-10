from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from daily_etf_analysis.api.app import app
from daily_etf_analysis.config.settings import Settings


class _FakeSystemConfigService:
    def get_system_config(self):  # type: ignore[no-untyped-def]
        return {"version": 1, "config": {"etf_list": ["US:QQQ"]}}

    def validate_system_config(self, updates):  # type: ignore[no-untyped-def]
        return {"valid": True, "issues": [], "candidate_config": updates}

    def update_system_config(self, expected_version, updates, actor):  # type: ignore[no-untyped-def]
        if expected_version == 0:
            raise ValueError("version_conflict: expected=0, actual=1")
        return {"version": 2, "config": updates}

    def get_system_config_schema(self):  # type: ignore[no-untyped-def]
        return {"fields": {"etf_list": {"type": "array[str]"}}}

    def list_system_config_audit(self, page=1, limit=20):  # type: ignore[no-untyped-def]
        return [
            {
                "id": 1,
                "version": 2,
                "actor": "admin",
                "action": "update",
                "changes": {"etf_list": ["US:QQQ"]},
                "created_at": "2026-03-10T10:00:00",
            }
        ]


class _ServiceWithSystemConfig:
    def __init__(self) -> None:
        self.system_config_service = _FakeSystemConfigService()

    def get_system_config(self):  # type: ignore[no-untyped-def]
        return self.system_config_service.get_system_config()

    def validate_system_config(self, updates):  # type: ignore[no-untyped-def]
        return self.system_config_service.validate_system_config(updates)

    def update_system_config(self, expected_version, updates, actor):  # type: ignore[no-untyped-def]
        return self.system_config_service.update_system_config(
            expected_version, updates, actor
        )

    def get_system_config_schema(self):  # type: ignore[no-untyped-def]
        return self.system_config_service.get_system_config_schema()

    def list_system_config_audit(self, page=1, limit=20):  # type: ignore[no-untyped-def]
        return self.system_config_service.list_system_config_audit(
            page=page, limit=limit
        )


def test_system_config_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    monkeypatch.setattr(router_module, "_service", lambda: _ServiceWithSystemConfig())

    auth_module = importlib.import_module("daily_etf_analysis.api.auth")
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(api_auth_enabled=False),
    )

    client = TestClient(app)

    get_resp = client.get("/api/v1/system/config")
    assert get_resp.status_code == 200
    assert get_resp.json()["version"] == 1

    validate_resp = client.post(
        "/api/v1/system/config/validate",
        json={"updates": {"etf_list": ["US:QQQ"]}},
    )
    assert validate_resp.status_code == 200
    assert validate_resp.json()["valid"] is True

    update_resp = client.put(
        "/api/v1/system/config",
        json={"expected_version": 1, "updates": {"etf_list": ["US:QQQ"]}},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["version"] == 2

    schema_resp = client.get("/api/v1/system/config/schema")
    assert schema_resp.status_code == 200
    assert "fields" in schema_resp.json()

    audit_resp = client.get("/api/v1/system/config/audit?page=1&limit=20")
    assert audit_resp.status_code == 200
    assert audit_resp.json()[0]["actor"] == "admin"


def test_system_config_update_requires_admin_token_when_auth_enabled(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    monkeypatch.setattr(router_module, "_service", lambda: _ServiceWithSystemConfig())

    auth_module = importlib.import_module("daily_etf_analysis.api.auth")
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(api_auth_enabled=True, api_admin_token="secret-token"),
    )

    client = TestClient(app)

    no_token = client.put(
        "/api/v1/system/config",
        json={"expected_version": 1, "updates": {"etf_list": ["US:QQQ"]}},
    )
    assert no_token.status_code == 401

    wrong = client.put(
        "/api/v1/system/config",
        json={"expected_version": 1, "updates": {"etf_list": ["US:QQQ"]}},
        headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 403

    ok = client.put(
        "/api/v1/system/config",
        json={"expected_version": 1, "updates": {"etf_list": ["US:QQQ"]}},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200


def test_system_config_version_conflict_returns_409(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    router_module = importlib.import_module("daily_etf_analysis.api.v1.router")
    monkeypatch.setattr(router_module, "_service", lambda: _ServiceWithSystemConfig())

    auth_module = importlib.import_module("daily_etf_analysis.api.auth")
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(api_auth_enabled=False),
    )

    client = TestClient(app)

    conflict = client.put(
        "/api/v1/system/config",
        json={"expected_version": 0, "updates": {"etf_list": ["US:QQQ"]}},
    )
    assert conflict.status_code == 409
