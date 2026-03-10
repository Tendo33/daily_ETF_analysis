from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from daily_etf_analysis.config.settings import get_settings

try:
    from scripts.backup_db import backup_database
    from scripts.restore_db import restore_database
except ModuleNotFoundError:
    # Allow running as a plain script: `python scripts/drill_recovery.py`
    from backup_db import backup_database  # type: ignore[no-redef]
    from restore_db import restore_database  # type: ignore[no-redef]


def run_recovery_drill(*, database_url: str, backup_dir: Path) -> dict[str, object]:
    start = time.perf_counter()
    backup_file = backup_database(database_url=database_url, output_dir=backup_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        restore_path = Path(tmpdir) / "drill_restore.db"
        restore_url = f"sqlite:///{restore_path}"
        restore_result = restore_database(
            database_url=restore_url,
            backup_file=backup_file,
        )

    rto_seconds = round(time.perf_counter() - start, 4)
    backup_mtime = backup_file.stat().st_mtime
    rpo_seconds = max(0.0, round(time.time() - backup_mtime, 4))

    return {
        "status": "ok",
        "database_url": database_url,
        "backup_file": str(backup_file),
        "restore_table_count": int(restore_result["table_count"]),
        "rto_seconds": rto_seconds,
        "rpo_seconds": rpo_seconds,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Disaster recovery drill")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--backup-dir", type=str, default="backups")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = str(args.database_url or settings.database_url)
    result = run_recovery_drill(
        database_url=database_url, backup_dir=Path(args.backup_dir)
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
