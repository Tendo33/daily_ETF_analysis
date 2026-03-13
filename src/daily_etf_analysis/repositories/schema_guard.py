from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from daily_etf_analysis.config.settings import Settings

REQUIRED_ALEMBIC_REVISION = "20260311_0004"


@dataclass(slots=True)
class SchemaGuardResult:
    ok: bool
    reason: str | None = None


def should_enforce_schema_guard(settings: Settings) -> bool:
    if settings.disable_schema_guard:
        return False
    return not os.getenv("PYTEST_CURRENT_TEST")


def ensure_schema_ready(engine: Engine, settings: Settings) -> None:
    if not should_enforce_schema_guard(settings):
        return
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        raise RuntimeError(_repair_hint("Missing alembic_version table"))

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    if not rows:
        raise RuntimeError(_repair_hint("Empty alembic_version table"))

    versions = {str(row[0]) for row in rows}
    if REQUIRED_ALEMBIC_REVISION not in versions:
        raise RuntimeError(
            _repair_hint(
                "Schema revision mismatch. "
                f"required={REQUIRED_ALEMBIC_REVISION}, current={sorted(versions)}"
            )
        )

    analysis_task_columns = {
        col["name"] for col in inspector.get_columns("analysis_tasks")
    }
    required_cols = {
        "skip_reason",
        "skipped_symbols_json",
        "analyzed_count",
        "skipped_count",
        "error_code",
        "run_id",
    }
    missing = sorted(required_cols - analysis_task_columns)
    if missing:
        raise RuntimeError(
            _repair_hint(f"analysis_tasks missing columns: {', '.join(missing)}")
        )


def check_schema_ready(engine: Engine, settings: Settings) -> SchemaGuardResult:
    try:
        ensure_schema_ready(engine, settings)
    except Exception as exc:  # noqa: BLE001
        return SchemaGuardResult(ok=False, reason=str(exc))
    return SchemaGuardResult(ok=True)


def _repair_hint(reason: str) -> str:
    return (
        "DATABASE_SCHEMA_NOT_READY: "
        f"{reason}. "
        "Run `uv run alembic upgrade head` (or `uv run python scripts/db_upgrade.py`) "
        "before starting analysis tasks."
    )
