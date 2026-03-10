from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from daily_etf_analysis.config.settings import get_settings


def backup_database(*, database_url: str, output_dir: Path) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise NotImplementedError("Only sqlite backup is implemented in phase4")

    db_path = Path(database_url.removeprefix("sqlite:///"))
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = output_dir / f"backup_{timestamp}.db"
    shutil.copy2(db_path, backup_file)
    return backup_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup database")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default="backups")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = str(args.database_url or settings.database_url)
    backup_file = backup_database(
        database_url=database_url, output_dir=Path(args.output_dir)
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "database_url": database_url,
                "backup_file": str(backup_file),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
