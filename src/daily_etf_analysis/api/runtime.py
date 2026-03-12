from __future__ import annotations

import threading

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.services import AnalysisService


class AppRuntime:
    def __init__(self, settings: Settings | None = None) -> None:
        self._lock = threading.Lock()
        self._settings = settings or get_settings()
        self._service = self._build_service(self._settings)

    def _build_service(self, settings: Settings) -> AnalysisService:
        service = AnalysisService(settings=settings)
        service.system_config_service.set_on_settings_applied(self._on_settings_applied)
        return service

    def _on_settings_applied(self, settings: Settings) -> None:
        new_service = self._build_service(settings)
        with self._lock:
            old_service = self._service
            self._service = new_service
        old_service.shutdown()

    def get_service(self) -> AnalysisService:
        with self._lock:
            return self._service

    def shutdown(self) -> None:
        with self._lock:
            service = self._service
        service.shutdown()
