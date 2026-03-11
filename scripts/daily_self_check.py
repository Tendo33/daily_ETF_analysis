from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine

from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.repositories.schema_guard import check_schema_ready
from daily_etf_analysis.scheduler.scheduler import next_run_for_cron


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    schema = check_schema_ready(engine, settings)

    now = datetime.now()
    schedule_check = {
        "cn_next": _to_iso(next_run_for_cron(settings.schedule_cron_cn, now)),
        "hk_next": _to_iso(next_run_for_cron(settings.schedule_cron_hk, now)),
        "us_next": _to_iso(next_run_for_cron(settings.schedule_cron_us, now)),
    }

    payload = {
        "schema_ready": schema.ok,
        "schema_reason": schema.reason,
        "llm_model_configured": bool(settings.litellm_model or settings.llm_model_list),
        "news_configured": bool(settings.tavily_api_keys),
        "notify_channels": settings.notify_channels,
        "schedule": schedule_check,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if schema.ok else 1


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
