from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from daily_etf_analysis.config.settings import get_settings


def restore_database(*, database_url: str, backup_file: Path) -> dict[str, object]:
    if not database_url.startswith("sqlite:///"):
        raise NotImplementedError("Only sqlite restore is implemented in phase4")

    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    db_path = Path(database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, db_path)

    table_count = _sqlite_table_count(db_path)
    return {
        "status": "ok",
        "database_url": database_url,
        "backup_file": str(backup_file),
        "table_count": table_count,
    }


def _sqlite_table_count(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore database")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--backup-file", type=str, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = str(args.database_url or settings.database_url)
    result = restore_database(
        database_url=database_url,
        backup_file=Path(args.backup_file),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
