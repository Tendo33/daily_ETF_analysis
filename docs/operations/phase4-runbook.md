# Phase 4 Operations Runbook

## Alert Severity

- `P1`: API unavailable, daily analysis full failure, backup/restore failure.
- `P2`: single provider degraded, queue pressure high, partial notify failure.
- `P3`: non-critical warning, fallback path triggered.

## Fault Triage

1. Check service health and metrics:
   - `GET /api/health`
   - `GET /api/metrics`
2. Check run execution and report quality:
   - `GET /api/v1/analysis/runs/{run_id}`
   - `GET /api/v1/reports/daily?date=YYYY-MM-DD&market=all&run_id={run_id}`
   - `GET /api/v1/history/signals?run_id={run_id}`
3. Check provider health:
   - `GET /api/v1/system/provider-health`
4. Check lifecycle cleanup preview:
   - `POST /api/v1/system/lifecycle/cleanup?dry_run=true`

## API Auth Boundary

- When `API_AUTH_ENABLED=true`, **all** `/api/v1/*` endpoints require:
  - `Authorization: Bearer <API_ADMIN_TOKEN>`
- `/api/health` and `/api/metrics` keep current public behavior.
- Auth failure semantics:
  - missing token -> `401`
  - wrong token -> `403`

## Task Status Semantics

- `pending/processing`: active execution lifecycle.
- `completed`: task finished（包含“全部被市场守卫跳过”的场景），跳过细节通过字段表达：
  - `skip_reason`
  - `skipped_symbols`
  - `analyzed_count` / `skipped_count`
- `failed`: execution error or timeout (`TASK_TIMEOUT` / `TASK_EXEC_FAILED` summary).

## Rollback And Recovery

1. Create backup:
   - `uv run python scripts/backup_db.py --output-dir backups`
2. Restore from backup:
   - `uv run python scripts/restore_db.py --backup-file backups/<file>.db`
3. Drill recovery and record RTO/RPO:
   - `uv run python scripts/drill_recovery.py --backup-dir backups`
4. For release gate rollback reference:
   - `.github/workflows/release_guard.yml`
5. Alembic migration rollback/forward:
   - upgrade to latest: `uv run alembic upgrade head`
   - rollback one revision: `uv run alembic downgrade 20260310_0002`
   - re-apply hardening revision: `uv run alembic upgrade head`
   - revision `20260311_0003` adds:
     - `analysis_tasks.skip_reason`
     - `analysis_tasks.skipped_symbols_json`
     - `analysis_tasks.analyzed_count`
     - `analysis_tasks.skipped_count`
     - index `ix_etf_analysis_reports_symbol_trade_date_id`
     - index `ix_etf_realtime_quotes_symbol_quote_time`

## On-call Checklist

- Verify latest CI quality gate passed: `.github/workflows/quality_gate.yml`
- Verify release guard checks passed: `.github/workflows/release_guard.yml`
- Verify security scan output:
  - `uv run python scripts/security_scan.py`
- Verify lifecycle retention execution log:
  - `POST /api/v1/system/lifecycle/cleanup?dry_run=false`
- Confirm daily smoke run succeeded:
  - `.github/workflows/daily_etf_analysis.yml`
