from __future__ import annotations

from sqlalchemy import create_engine, text

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.repositories.schema_guard import check_schema_ready


def test_schema_guard_fails_without_alembic_version(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DISABLE_SCHEMA_GUARD", raising=False)

    db_path = tmp_path / "guard_missing.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    settings = Settings(database_url=f"sqlite:///{db_path}")

    result = check_schema_ready(engine, settings)
    assert result.ok is False
    assert "DATABASE_SCHEMA_NOT_READY" in str(result.reason)


def test_schema_guard_passes_when_revision_and_columns_present(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DISABLE_SCHEMA_GUARD", raising=False)

    db_path = tmp_path / "guard_ok.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        conn.execute(
            text("INSERT INTO alembic_version(version_num) VALUES ('20260311_0004')")
        )
        conn.execute(
            text(
                "CREATE TABLE analysis_tasks ("
                "task_id TEXT, status TEXT, symbols_json TEXT, force_refresh INTEGER, error TEXT,"
                "skip_reason TEXT, skipped_symbols_json TEXT, analyzed_count INTEGER, skipped_count INTEGER,"
                "error_code TEXT, run_id TEXT, created_at TEXT, updated_at TEXT)"
            )
        )

    settings = Settings(database_url=f"sqlite:///{db_path}")
    result = check_schema_ready(engine, settings)
    assert result.ok is True


def test_schema_guard_disabled_by_settings(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("DISABLE_SCHEMA_GUARD", "true")

    db_path = tmp_path / "guard_disabled.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{db_path}")

    result = check_schema_ready(engine, settings)
    assert result.ok is True
