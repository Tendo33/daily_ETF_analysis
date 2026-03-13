# daily_ETF_analysis

![Daily ETF Analysis Banner](assets/banner.png)

[中文文档](README_CN.md)

`daily_ETF_analysis` is a production-oriented ETF analysis service for CN/HK/US markets.
It focuses on stable, structured outputs (scores, trend/action signals, confidence, risk alerts, run contracts), not only free-form text.

## Table of Contents

1. [Overview](#overview)
2. [Core Features](#core-features)
3. [Architecture](#architecture)
4. [Project Layout](#project-layout)
5. [Quick Start](#quick-start)
6. [Run Modes](#run-modes)
7. [Configuration](#configuration)
8. [API Guide](#api-guide)
9. [Database and Migrations](#database-and-migrations)
10. [Reports and Artifacts](#reports-and-artifacts)
11. [Observability and Operations](#observability-and-operations)
12. [Security](#security)
13. [Development Workflow](#development-workflow)
14. [CI Workflows](#ci-workflows)
15. [Troubleshooting](#troubleshooting)
16. [Documentation Map](#documentation-map)
17. [License and Disclaimer](#license-and-disclaimer)

## Overview

This service analyzes a configurable ETF universe using:

- Multi-source market data providers with resilience controls
- News enrichment (Tavily)
- LLM-based decision generation (OpenAI-compatible only)
- Persistent run/task/report history via SQLite + SQLAlchemy + Alembic

Symbol format is unified as `<MARKET>:<CODE>`, for example:

- `CN:159659`
- `US:QQQ`
- `HK:02800`

## Core Features

- Unified analysis runs with status tracking (`pending -> processing -> completed|failed|cancelled`)
- Cross-market ETF and index mapping contracts
- Data provider priority and fallback matrix:
  - `efinance -> akshare -> tushare/pytdx -> baostock -> yfinance`
- Provider resilience: retry, backoff, circuit breaker, provider health API
- Structured decision outputs:
  - `score`, `trend`, `action`, `confidence`, `risk_alerts`, `summary`, `key_points`, `horizon`, `rationale`
- History APIs for signal retrieval and run replay
- Built-in backtest endpoints and per-symbol performance views
- System config APIs (read/validate/update/schema/audit)
- Data lifecycle retention cleanup
- Multi-channel notifications:
  - Feishu, WeChat, Telegram, Email
- Prometheus-style metrics endpoint (`/api/metrics`)

## Architecture

```mermaid
flowchart LR
    A["Client (CLI/API/Scheduler)"] --> B["FastAPI / CLI Entrypoints"]
    B --> C["AnalysisService"]
    C --> D["Market Data Providers"]
    C --> E["News Provider (Tavily)"]
    C --> F["LLM Analyzer (OpenAI-compatible)"]
    C --> G["Repository (SQLAlchemy)"]
    G --> H["SQLite"]
    C --> I["Report Renderer"]
    C --> J["Notification Manager"]
```

Layering follows:

- `api`: HTTP contracts and auth guards
- `services`: orchestration and business flow
- `repositories`: persistence and schema guard
- `domain`: core models/enums/value normalization

## Project Layout

```text
src/daily_etf_analysis/
├── api/                # FastAPI app, auth, v1 routes/schemas
├── backtest/           # Backtest engine and models
├── cli/                # CLI entrypoints
├── config/             # Pydantic settings and validation
├── core/               # Trading calendar and time utilities
├── domain/             # ETF domain models and symbol rules
├── llm/                # ETF decision engine (OpenAI-compatible)
├── notifications/      # Feishu/WeChat/Telegram/Email + markdown image
├── observability/      # metrics and logging
├── pipelines/          # Daily workflow pipeline
├── providers/          # Market data + news providers
├── repositories/       # DB access + schema guard
├── reports/            # Markdown rendering
└── scheduler/          # Cron scheduler

scripts/                # Operational and maintenance scripts
docs/operations/        # Runbooks (phase3/phase4)
examples/               # Small usage examples
tests/                  # Unit/integration/contract tests
```

## Quick Start

### 1. Prerequisites

- Python `>=3.11`
- [uv](https://docs.astral.sh/uv/)
- Network access to your configured providers/LLM endpoints

### 2. Install dependencies

```bash
uv sync --all-extras
```

### 3. Create local env file

```bash
cp .env.example .env
```

### 4. Minimal configuration

At minimum, set your target ETF list and DB path (defaults are already provided):

```env
ETF_LIST=CN:159659,US:QQQ,HK:02800
DATABASE_URL=sqlite:///./data/daily_etf_analysis.db
```

For full-quality output (recommended), configure LLM + news:

```env
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-xxxx
# OPENAI_BASE_URL=https://api.openai.com
TAVILY_API_KEYS=tvly-xxxx
# TAVILY_BASE_URL=https://tavily.ivanli.cc/api/tavily
```

### 5. Start API server

```bash
uv run uvicorn daily_etf_analysis.api.app:app --host 0.0.0.0 --port 8000
```

### 6. Verify health

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/metrics
```

### 7. Trigger one analysis run

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analysis/runs \
  -H "Content-Type: application/json" \
  -d '{"symbols":["CN:159659","US:QQQ","HK:02800"]}'
```

OpenAPI docs:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## Run Modes

### API only

```bash
uv run uvicorn daily_etf_analysis.api.app:app --host 0.0.0.0 --port 8000
```

### One-shot daily analysis (CLI)

```bash
uv run python scripts/run_daily_analysis.py
```

Common options:

```bash
uv run python scripts/run_daily_analysis.py --force-run --market cn
uv run python scripts/run_daily_analysis.py --symbols CN:159659,US:QQQ --skip-notify
uv run python scripts/run_daily_analysis.py --wait-timeout-seconds 900 --poll-interval-seconds 2
```

### Main entrypoint (`main.py`)

```bash
# Run API + scheduler (if enabled)
uv run python main.py --serve --schedule

# API only
uv run python main.py --serve-only

```

### Dedicated scheduler process

```bash
uv run python scripts/run_scheduler.py
```

Notes:

- Scheduler cron expression format is `sec min hour day month weekday` (6 fields).
- `scripts/run_scheduler.py` currently executes CN market runs only by design.

## Configuration

All config is loaded via `pydantic-settings` from:

1. environment variables
2. `.env`
3. defaults in code

### Key configuration groups

- Universe and mappings
  - `ETF_LIST`, `INDEX_PROXY_MAP`, `MARKETS_ENABLED`
- Data source priority and resilience
  - `REALTIME_SOURCE_PRIORITY`
  - `PROVIDER_MAX_RETRIES`, `PROVIDER_BACKOFF_MS`, `PROVIDER_CIRCUIT_FAIL_THRESHOLD`, `PROVIDER_CIRCUIT_RESET_SECONDS`
- LLM (OpenAI-compatible only)
  - `OPENAI_MODEL`, `OPENAI_API_KEY(S)`, `OPENAI_BASE_URL`
- News
  - `TAVILY_API_KEYS`, `TAVILY_BASE_URL`, `NEWS_MAX_AGE_DAYS`, `NEWS_PROVIDER_PRIORITY`
- Notifications
  - `NOTIFY_CHANNELS`, `FEISHU_WEBHOOK_URL`, `WECHAT_WEBHOOK_URL`, `TELEGRAM_*`, `EMAIL_*`
- Runtime and reliability
  - `TASK_MAX_CONCURRENCY`, `TASK_TIMEOUT_SECONDS`
- Retention / lifecycle
  - `RETENTION_TASK_DAYS`, `RETENTION_REPORT_DAYS`, `RETENTION_QUOTE_DAYS`
- API auth
  - `API_AUTH_ENABLED`, `API_ADMIN_TOKEN`
- Scheduler
  - `SCHEDULE_ENABLED`, `SCHEDULE_CRON_CN/HK/US`

### Auth behavior

When `API_AUTH_ENABLED=true`:

- all `/api/v1/*` endpoints require `Authorization: Bearer <API_ADMIN_TOKEN>`
- `/api/health` and `/api/metrics` remain public

When `API_AUTH_ENABLED=false` (default):

- `/api/v1/*` works without token

## API Guide

### Typical flow

1. Create run

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analysis/runs \
  -H "Content-Type: application/json" \
  -d '{"symbols":["US:QQQ"],"force_refresh":false}'
```

2. Query run status

```bash
curl http://127.0.0.1:8000/api/v1/analysis/runs/<run_id>
```

3. Fetch daily report contract

```bash
curl "http://127.0.0.1:8000/api/v1/reports/daily?date=2026-03-10&market=all&run_id=<run_id>"
```

4. Fetch historical signals

```bash
curl "http://127.0.0.1:8000/api/v1/history/signals?symbol=US:QQQ&run_id=<run_id>"
```

### Endpoint index

- Analysis
  - `POST /api/v1/analysis/runs`
  - `GET /api/v1/analysis/runs/{run_id}`
- Reports and history
  - `GET /api/v1/reports/daily`
  - `GET /api/v1/history/signals`
- ETF and index mapping
  - `GET /api/v1/etfs`
  - `PUT /api/v1/etfs`
  - `GET /api/v1/index-mappings`
  - `PUT /api/v1/index-mappings`
  - `GET /api/v1/etfs/{symbol}/quote`
  - `GET /api/v1/etfs/{symbol}/history`
  - `GET /api/v1/index-comparisons`
- Backtest
  - `POST /api/v1/backtest/run`
  - `GET /api/v1/backtest/results`
  - `GET /api/v1/backtest/performance`
  - `GET /api/v1/backtest/performance/{symbol}`
- System
  - `GET /api/v1/system/provider-health`
  - `GET /api/v1/system/config`
  - `POST /api/v1/system/config/validate`
  - `PUT /api/v1/system/config`
  - `GET /api/v1/system/config/schema`
  - `GET /api/v1/system/config/audit`
  - `POST /api/v1/system/lifecycle/cleanup`
- Public
  - `GET /api/health`
  - `GET /api/metrics`

## Database and Migrations

Default database is SQLite:

- `DATABASE_URL=sqlite:///./data/daily_etf_analysis.db`

Schema management:

```bash
# apply latest migrations
uv run alembic upgrade head

# rollback one revision (example)
uv run alembic downgrade 20260310_0002
```

Safe upgrade helper with backup + post-check:

```bash
uv run python scripts/db_upgrade.py --backup-dir data/backups
```

Backup / restore / DR drill:

```bash
uv run python scripts/backup_db.py --output-dir backups
uv run python scripts/restore_db.py --backup-file backups/<backup>.db
uv run python scripts/drill_recovery.py --backup-dir backups
```

## Reports and Artifacts

Daily run output files:

- `reports/daily_etf_<date>_<taskid8>.json`
- `reports/report_YYYYMMDD_<taskid8>.md`
- `reports/report_YYYYMMDD.md` (latest compatible path, overwritten)

CLI stdout returns a structured JSON summary including:

- task/run IDs
- aggregate status
- report paths
- decision quality
- failures
- per-channel notification results

## Observability and Operations

### Config and provider checks

```bash
uv run python scripts/test_env.py --config
uv run python scripts/test_env.py --fetch --symbol CN:159659
uv run python scripts/test_env.py --llm
```

### Daily self-check

```bash
uv run python scripts/daily_self_check.py
```

### Security baseline scan

```bash
uv run python scripts/security_scan.py
```

### Runbooks

- Phase 3: `docs/operations/phase3-runbook.md`
- Phase 4: `docs/operations/phase4-runbook.md`

## Security

- Keep `.env` local and never commit real secrets.
- Enable API token auth for non-local environments:

```env
API_AUTH_ENABLED=true
API_ADMIN_TOKEN=<strong-random-token>
```

- Notification channels are fail-soft by design:
  - missing credentials return `disabled`
  - one channel failure does not block others

## Development Workflow

### Required quality gates

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```

Frontend checks (run only if `frontend/` exists):

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

### Useful local commands

```bash
python scripts/setup_pre_commit.py
uv run pytest tests/test_api_v1.py
uv run pytest tests/test_end_to_end_analysis_flow.py
```

## CI Workflows

- `.github/workflows/daily_etf_analysis.yml`: scheduled/manual daily analysis
- `.github/workflows/quality_gate.yml`: lint/type/test checks
- `.github/workflows/release_guard.yml`: release safety checks and rollback gates

## Troubleshooting

### 1. `No LLM configured`

- Set one of:
  - `OPENAI_MODEL`
  - `OPENAI_API_KEY` / `OPENAI_API_KEYS`

### 2. API returns `401/403` on `/api/v1/*`

- Check `API_AUTH_ENABLED`
- If enabled, send `Authorization: Bearer <API_ADMIN_TOKEN>`

### 3. Empty/weak report quality

- Check provider health: `GET /api/v1/system/provider-health`
- Verify Tavily keys and `NEWS_MAX_AGE_DAYS`
- Verify OpenAI model/key configuration

### 4. Scheduler does not trigger

- Ensure `SCHEDULE_ENABLED=true`
- Verify cron expressions use 6 fields (`sec min hour day month weekday`)
- Confirm market is open and after market close time

### 5. `security_scan.py` reports pip-audit tool error

- Install `pip-audit` in environment if missing, then rerun

## Documentation Map

- [Settings Guide](doc/SETTINGS_GUIDE.md)
- [SDK Usage](doc/SDK_USAGE.md)
- [Pre-commit Guide](doc/PRE_COMMIT_GUIDE.md)
- [Models Guide](doc/MODELS_GUIDE.md)
- [Architecture report](docs/PROJECT_ARCHITECTURE_LLM_REPORT.md)
- [Phase 3 runbook](docs/operations/phase3-runbook.md)
- [Phase 4 runbook](docs/operations/phase4-runbook.md)

## License and Disclaimer

- License: [MIT](LICENSE)
- Research use only. This project does **not** provide investment advice.
