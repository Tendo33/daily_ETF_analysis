# Phase 3 Operations Runbook

## 1. End-to-End Daily Path

1. Trigger analysis task:
   - `uv run python scripts/run_daily_analysis.py --skip-notify`
2. Verify generated artifacts:
   - JSON: `reports/daily_etf_<date>_<taskid>.json`
   - Markdown: `reports/report_YYYYMMDD.md`
3. Verify history data:
   - `GET /api/v1/history?page=1&limit=20`
   - `GET /api/v1/history/{record_id}`
4. Run backtest and inspect performance:
   - `POST /api/v1/backtest/run`
   - `GET /api/v1/backtest/performance?run_id=<run_id>`
5. Check notification delivery results:
   - CLI JSON field `notification_channels`

## 2. Notification Troubleshooting

1. Check enabled channels in env:
   - `NOTIFY_CHANNELS`
2. Missing channel credentials should return `disabled` and not block report output.
3. If one channel fails, verify another channel still sends.

## 3. System Config API

1. Read current config:
   - `GET /api/v1/system/config`
2. Validate updates before apply:
   - `POST /api/v1/system/config/validate`
3. Apply updates with optimistic version check:
   - `PUT /api/v1/system/config`
4. Inspect schema and audit logs:
   - `GET /api/v1/system/config/schema`
   - `GET /api/v1/system/config/audit?page=1&limit=20`

## 4. Auth Switch and Rollback

1. Enable auth:
   - `API_AUTH_ENABLED=true`
   - `API_ADMIN_TOKEN=<strong-token>`
2. Verify protected write APIs with Bearer token.
3. Rollback auth quickly:
   - set `API_AUTH_ENABLED=false`
   - restart service

## 5. CI Contracts

1. Workflow file: `.github/workflows/daily_etf_analysis.yml`
2. Required contracts:
   - dispatch inputs: `force_run/symbols/market/skip_notify`
   - `concurrency.group`
   - config probe step
   - smoke step with `--skip-notify`
   - artifact upload for `reports/` and `logs/`

## 6. Quality Gates

Run before merge:

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```
