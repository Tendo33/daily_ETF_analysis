from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from scripts.backup_db import backup_database
from scripts.drill_recovery import run_recovery_drill
from scripts.restore_db import restore_database


def _create_sqlite_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY, value TEXT)"
        )
        conn.execute("INSERT INTO sample(value) VALUES ('x')")
        conn.commit()
    finally:
        conn.close()


def test_backup_restore_and_drill(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source_db = tmp_path / "source.db"
    _create_sqlite_db(source_db)
    db_url = f"sqlite:///{source_db}"

    backup_file = backup_database(database_url=db_url, output_dir=tmp_path)
    assert backup_file.exists()
    assert backup_file.name.startswith("backup_")

    restored_db = tmp_path / "restored.db"
    restore_result = restore_database(
        database_url=f"sqlite:///{restored_db}",
        backup_file=backup_file,
    )
    assert restored_db.exists()
    assert int(restore_result["table_count"]) >= 1

    drill_result = run_recovery_drill(database_url=db_url, backup_dir=tmp_path)
    assert float(drill_result["rto_seconds"]) >= 0
    assert float(drill_result["rpo_seconds"]) >= 0
    assert int(drill_result["restore_table_count"]) >= 1


def test_drill_recovery_cli_help_runs() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/drill_recovery.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "Disaster recovery drill" in completed.stdout
