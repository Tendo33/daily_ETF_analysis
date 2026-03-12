from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


class _FakeRuntime:
    def __init__(self) -> None:
        self.closed = False

    def get_service(self):  # type: ignore[no-untyped-def]
        return object()

    def shutdown(self) -> None:
        self.closed = True


def test_lifespan_creates_and_closes_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app_module = importlib.import_module("daily_etf_analysis.api.app")
    runtime = _FakeRuntime()
    monkeypatch.setattr(app_module, "_runtime_provider", lambda: runtime)

    with TestClient(app_module.app) as client:
        assert client.app.state.runtime is runtime

    assert runtime.closed is True
