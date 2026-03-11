from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine

from daily_etf_analysis.config.settings import get_settings
from daily_etf_analysis.repositories.schema_guard import check_schema_ready


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe DB upgrade helper")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--backup-dir", type=str, default="data/backups")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = args.database_url or settings.database_url
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_file = _sqlite_file_from_url(database_url)
    if db_file is None:
        print("Only sqlite:/// URLs are supported by this helper.")
        return 2

    backup_path = (
        backup_dir / f"{db_file.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    )
    if db_file.exists():
        shutil.copy2(db_file, backup_path)
        print(f"Backup created: {backup_path}")
    else:
        print("Database file does not exist yet; migration will initialize schema.")

    env = {**os.environ, "DATABASE_URL": database_url}
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        _restore_if_needed(db_file, backup_path)
        print(f"Migration failed and rollback applied: {exc}")
        return 1

    engine = create_engine(database_url, future=True)
    result = check_schema_ready(engine, settings)
    if not result.ok:
        _restore_if_needed(db_file, backup_path)
        print(f"Post-upgrade validation failed and rollback applied: {result.reason}")
        return 1

    print("Database upgrade completed and validated.")
    return 0


def _restore_if_needed(db_file: Path, backup_path: Path) -> None:
    if backup_path.exists():
        shutil.copy2(backup_path, db_file)


def _sqlite_file_from_url(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    value = database_url[len(prefix) :]
    if value.startswith("./"):
        value = value[2:]
    return Path(value).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
