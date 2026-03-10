# Phase 4 Operations Runbook

## Alert Severity

- `P1`: API unavailable, daily analysis full failure, backup/restore failure.
- `P2`: single provider degraded, queue pressure high, partial notify failure.
- `P3`: non-critical warning, fallback path triggered.

## Fault Triage

1. Check service health and metrics:
   - `GET /api/health`
   - `GET /api/metrics`
2. Check queue pressure and task status:
   - `GET /api/v1/analysis/tasks?limit=50`
3. Check provider health:
   - `GET /api/v1/system/provider-health`
4. Check lifecycle cleanup preview:
   - `POST /api/v1/system/lifecycle/cleanup?dry_run=true`

## Rollback And Recovery

1. Create backup:
   - `uv run python scripts/backup_db.py --output-dir backups`
2. Restore from backup:
   - `uv run python scripts/restore_db.py --backup-file backups/<file>.db`
3. Drill recovery and record RTO/RPO:
   - `uv run python scripts/drill_recovery.py --backup-dir backups`
4. For release gate rollback reference:
   - `.github/workflows/release_guard.yml`

## On-call Checklist

- Verify latest CI quality gate passed: `.github/workflows/quality_gate.yml`
- Verify release guard checks passed: `.github/workflows/release_guard.yml`
- Verify security scan output:
  - `uv run python scripts/security_scan.py`
- Verify lifecycle retention execution log:
  - `POST /api/v1/system/lifecycle/cleanup?dry_run=false`
- Confirm daily smoke run succeeded:
  - `.github/workflows/daily_etf_analysis.yml`
