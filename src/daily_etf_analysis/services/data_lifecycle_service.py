from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.core.time import utc_now_naive
from daily_etf_analysis.repositories import EtfRepository

logger = logging.getLogger(__name__)


class DataLifecycleService:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: EtfRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or EtfRepository(self.settings)

    def cleanup(self, *, dry_run: bool = True, actor: str = "system") -> dict[str, Any]:
        now = utc_now_naive()
        task_cutoff = now - timedelta(days=self.settings.retention_task_days)
        report_cutoff = now - timedelta(days=self.settings.retention_report_days)
        quote_cutoff = now - timedelta(days=self.settings.retention_quote_days)

        impacted = self.repository.count_expired_records(
            task_created_before=task_cutoff,
            report_created_before=report_cutoff,
            quote_time_before=quote_cutoff,
        )

        deleted = {"tasks": 0, "reports": 0, "quotes": 0}
        if not dry_run:
            deleted = self.repository.delete_expired_records(
                task_created_before=task_cutoff,
                report_created_before=report_cutoff,
                quote_time_before=quote_cutoff,
            )

        payload = {
            "dry_run": dry_run,
            "actor": actor,
            "executed_at": now.isoformat(),
            "retention_days": {
                "tasks": self.settings.retention_task_days,
                "reports": self.settings.retention_report_days,
                "quotes": self.settings.retention_quote_days,
            },
            "impacted": impacted,
            "deleted": deleted,
        }
        logger.info("lifecycle_cleanup %s", payload)
        return payload
