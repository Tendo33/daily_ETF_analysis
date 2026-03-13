__all__ = [
    "AnalysisService",
    "DataLifecycleService",
    "SystemConfigService",
    "TaskManager",
    "compute_factors",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "AnalysisService":
        from daily_etf_analysis.services.analysis_service import AnalysisService

        return AnalysisService
    if name == "DataLifecycleService":
        from daily_etf_analysis.services.data_lifecycle_service import (
            DataLifecycleService,
        )

        return DataLifecycleService
    if name == "SystemConfigService":
        from daily_etf_analysis.services.system_config_service import (  # noqa: I001
            SystemConfigService,
        )

        return SystemConfigService
    if name == "TaskManager":
        from daily_etf_analysis.services.task_manager import TaskManager

        return TaskManager
    if name == "compute_factors":
        from daily_etf_analysis.services.factor_engine import compute_factors

        return compute_factors
    raise AttributeError(name)
