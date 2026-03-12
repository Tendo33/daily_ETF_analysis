from __future__ import annotations

from types import SimpleNamespace

import main as main_module
from daily_etf_analysis.config.settings import Settings


class _FakeLogger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


class _FakeScheduler:
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.force_enable: bool | None = None
        self.stop_called = False

    def start(self, force_enable: bool = False) -> bool:
        self.force_enable = force_enable
        return False

    def stop(self) -> None:
        self.stop_called = True


def test_main_schedule_flag_forces_enable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    args = SimpleNamespace(
        schedule=True,
        serve=False,
        serve_only=False,
        market_review=False,
        no_notify=True,
        force_run=False,
        host="0.0.0.0",
        port=8000,
    )
    fake_logger = _FakeLogger()
    fake_scheduler = _FakeScheduler()

    monkeypatch.setattr(main_module, "parse_args", lambda: args)
    monkeypatch.setattr(
        main_module, "get_settings", lambda: Settings(schedule_enabled=False)
    )
    monkeypatch.setattr(main_module, "AnalysisService", lambda settings: object())
    monkeypatch.setattr(main_module, "NotificationManager", lambda settings: object())
    monkeypatch.setattr(main_module, "EtfScheduler", lambda **kwargs: fake_scheduler)
    monkeypatch.setattr(main_module, "logger", fake_logger)

    def _stop_loop(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(main_module.time, "sleep", _stop_loop)

    rc = main_module.main()

    assert rc == 0
    assert fake_scheduler.force_enable is True
    assert all("Scheduler started" not in msg for msg in fake_logger.infos)
