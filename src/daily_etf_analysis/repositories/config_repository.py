from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func, select

from daily_etf_analysis.repositories.models import (
    SystemConfigAuditLogORM,
    SystemConfigSnapshotORM,
)


class ConfigRepositoryMixin:
    def session(self) -> Any:
        raise NotImplementedError

    def create_system_config_snapshot(
        self, config_payload: dict[str, Any], actor: str, expected_version: int | None
    ) -> int:
        with self.session() as db:
            latest_version = (
                db.execute(select(func.max(SystemConfigSnapshotORM.version))).scalar()
                or 0
            )
            if expected_version is not None and expected_version != int(latest_version):
                raise ValueError(
                    f"version_conflict: expected={expected_version}, actual={latest_version}"
                )
            new_version = int(latest_version) + 1
            db.add(
                SystemConfigSnapshotORM(
                    version=new_version,
                    config_json=json.dumps(config_payload, ensure_ascii=False),
                    created_by=actor,
                )
            )
            return new_version

    def get_latest_system_config_snapshot(self) -> dict[str, Any] | None:
        with self.session() as db:
            row = (
                db.execute(
                    select(SystemConfigSnapshotORM).order_by(
                        desc(SystemConfigSnapshotORM.version)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return {
                "version": row.version,
                "config": json.loads(row.config_json),
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat(),
            }

    def create_system_config_audit_log(
        self, version: int, actor: str, action: str, changes: dict[str, Any]
    ) -> None:
        with self.session() as db:
            db.add(
                SystemConfigAuditLogORM(
                    version=version,
                    actor=actor,
                    action=action,
                    changes_json=json.dumps(changes, ensure_ascii=False),
                )
            )

    def list_system_config_audit_logs(
        self, page: int = 1, limit: int = 20
    ) -> list[dict[str, Any]]:
        offset = max(0, (page - 1) * limit)
        with self.session() as db:
            rows = (
                db.execute(
                    select(SystemConfigAuditLogORM)
                    .order_by(desc(SystemConfigAuditLogORM.id))
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "version": row.version,
                    "actor": row.actor,
                    "action": row.action,
                    "changes": json.loads(row.changes_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def delete_system_config_snapshot(self, version: int) -> None:
        with self.session() as db:
            db.query(SystemConfigSnapshotORM).filter(
                SystemConfigSnapshotORM.version == version
            ).delete()
