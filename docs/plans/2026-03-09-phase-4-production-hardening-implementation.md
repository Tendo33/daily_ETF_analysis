# Phase 4 Production Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Phase 3 功能闭环基础上，完成生产级加固（安全、可靠性、可追责、可观测、可恢复），使系统具备长期稳定运行与运维治理能力。

**Architecture:** 延续现有 `api -> services -> repositories -> providers` 分层，不引入前端。Phase 4 聚焦“横切能力”而非新增分析功能：为写接口增加鉴权和审计、为任务执行增加幂等保障、为数据与通知增加可观测和追踪、为发布与运维增加门禁和 runbook。所有变更默认向后兼容，新增能力通过配置显式开启。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, pydantic-settings, GitHub Actions.

---

## Scope 和完成定义

- In Scope:
  - 写接口最小鉴权与角色分级（operator/admin）。
  - 配置变更持久化与审计日志。
  - 分析任务幂等键与重复提交抑制（API + CLI + CI）。
  - 数据质量/新鲜度观测 API。
  - 通知投递日志与失败重试策略统一。
  - 发布门禁与运维 runbook。
- Out of Scope:
  - 前端管理台。
  - 新增市场或新策略模型。
  - 大规模分布式改造（如消息队列重构）。
- Definition of Done:
  - 关键写接口具备可开关鉴权，未授权请求被拒绝。
  - 配置更新可追踪（谁、何时、改了什么、版本号）。
  - 相同幂等键请求不会重复创建任务。
  - 可通过 API 看到数据新鲜度与质量告警。
  - 通知失败可追踪并支持重试，不影响主任务完成。
  - CI 包含质量门禁 + 迁移校验 + 最小 smoke。
  - `uv run ruff check src tests scripts`、`uv run ruff format --check src tests scripts`、`uv run mypy src`、`uv run pytest` 全部通过。

## Milestones（建议 2 周）

1. M1（D1-D2）：鉴权与角色体系（仅保护写操作）。
2. M2（D3-D4）：配置持久化与审计。
3. M3（D5-D6）：任务幂等与重复提交抑制。
4. M4（D7-D8）：数据质量与新鲜度观测。
5. M5（D9-D10）：通知投递日志与重试治理。
6. M6（D11-D12）：CI 发布门禁强化。
7. M7（D13-D14）：回归、文档、runbook 收敛。

## Task 1: 写接口鉴权与角色分级

**Files:**
- Create: `src/daily_etf_analysis/security/auth.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_api_auth.py`

**Step 1: Write the failing tests**
- 未携带 token 访问写接口（`POST /analysis/run`, `PUT /etfs`, `PUT /index-mappings`）返回 401。
- `operator` 可运行任务但不可更新系统配置（后续 Task 2 接口）。
- `admin` 可执行全部写操作。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_api_auth.py -v`
- Expected: FAIL（鉴权依赖不存在）

**Step 3: Write minimal implementation**
- 新增配置：
  - `API_AUTH_ENABLED=false`
  - `API_OPERATOR_TOKENS=...`
  - `API_ADMIN_TOKENS=...`
- 在 router 写接口挂载鉴权 dependency，读接口保持匿名可读。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_api_auth.py -v`
- Expected: PASS

## Task 2: 配置持久化与审计日志

**Files:**
- Create: `alembic/versions/20260309_0004_system_config_audit.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Create: `src/daily_etf_analysis/services/system_config_service.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_system_config_audit.py`

**Step 1: Write the failing tests**
- 配置更新会写入 `system_config_audit_logs`（含 actor、before、after、version）。
- 版本冲突返回 409。
- 读取配置时敏感字段脱敏。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_system_config_audit.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 仅新增前向迁移，不修改历史迁移文件。
- API：
  - `GET /api/v1/system/config`
  - `PUT /api/v1/system/config`
  - `GET /api/v1/system/config/audit`
- 更新后触发 `reload_settings()`。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_system_config_audit.py -v`
- Expected: PASS

## Task 3: 任务幂等键与重复提交抑制

**Files:**
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Modify: `src/daily_etf_analysis/services/task_manager.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Modify: `src/daily_etf_analysis/cli/run_daily_analysis.py`
- Test: `tests/test_idempotent_run.py`

**Step 1: Write the failing tests**
- 相同 `idempotency_key` + 相同参数重复请求返回同一 `task_id`。
- 不同 key 返回不同任务。
- CLI 支持 `--idempotency-key` 并透传到服务层。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_idempotent_run.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- `analysis_tasks` 增加 `idempotency_key` 字段与索引（允许空）。
- service 先查重再创建任务。
- GitHub workflow 手动触发时自动生成 key（基于 run_id + 参数哈希）。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_idempotent_run.py -v`
- Expected: PASS

## Task 4: 数据质量与新鲜度观测

**Files:**
- Create: `src/daily_etf_analysis/observability/data_quality.py`
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_data_quality_api.py`

**Step 1: Write the failing tests**
- `GET /api/v1/system/data-quality` 返回：
  - `symbol`
  - `latest_bar_date`
  - `latest_quote_time`
  - `bar_staleness_days`
  - `quote_staleness_minutes`
  - `status`（ok/warn/stale）
- 支持 `market` 过滤。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_data_quality_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 从 repository 聚合最新行情与日线时间戳。
- 通过配置阈值判定告警：
  - `DATA_QUALITY_MAX_BAR_STALENESS_DAYS`
  - `DATA_QUALITY_MAX_QUOTE_STALENESS_MINUTES`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_data_quality_api.py -v`
- Expected: PASS

## Task 5: 通知投递日志与重试治理

**Files:**
- Create: `alembic/versions/20260309_0005_notification_delivery_logs.py`
- Modify: `src/daily_etf_analysis/notifications/manager.py`（若 Phase 3 已创建）
- Modify: `src/daily_etf_analysis/notifications/feishu.py`
- Modify: `src/daily_etf_analysis/cli/run_daily_analysis.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Test: `tests/test_notification_delivery_logs.py`

**Step 1: Write the failing tests**
- 每次发送写入 delivery log（channel/status/error/retry_count/task_id）。
- 渠道失败会按配置重试并记录最终状态。
- 通知失败不改变任务最终状态。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_notification_delivery_logs.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增配置：
  - `NOTIFY_MAX_RETRIES`
  - `NOTIFY_BACKOFF_MS`
- 在 daily runner 汇总每个渠道投递结果并落库。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_notification_delivery_logs.py -v`
- Expected: PASS

## Task 6: CI 发布门禁强化

**Files:**
- Modify: `.github/workflows/daily_etf_analysis.yml`
- Create: `.github/workflows/quality_gate.yml`
- Modify: `README.md`
- Test: `tests/test_ci_contracts.py`

**Step 1: Write the failing tests/checks**
- 校验 workflow 包含：
  - 质量门禁（ruff/mypy/pytest）
  - Alembic `upgrade --sql` 或 `upgrade head` 校验步骤
  - daily runner smoke（`--skip-notify`）

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_ci_contracts.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增 `quality_gate.yml`（PR 触发）。
- `daily_etf_analysis.yml` 增加 migration probe 与 smoke step。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_ci_contracts.py -v`
- Expected: PASS

## Task 7: 运维文档与演练脚本

**Files:**
- Create: `docs/operations/phase4-runbook.md`
- Create: `scripts/ops_smoke_check.py`
- Modify: `README.md`
- Test: `tests/test_ops_smoke_check.py`

**Step 1: Write the failing tests**
- 脚本输出关键探针结果：
  - DB 连接
  - provider health API
  - data-quality API
  - 最近任务状态

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_ops_smoke_check.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增 one-command 运维自检脚本。
- runbook 增加故障分级、回滚步骤、常见告警处理。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_ops_smoke_check.py -v`
- Expected: PASS

## Risks & Mitigations

- 风险: 鉴权开关误配置导致现网接口全部拒绝。
  - 应对: 默认 `API_AUTH_ENABLED=false`，并在启动日志明确提示当前模式。
- 风险: 配置审计日志增长过快。
  - 应对: 增加按天归档策略与保留天数配置。
- 风险: 幂等键设计不当导致任务被误复用。
  - 应对: key + 参数摘要联合校验；不一致时返回 409。
- 风险: 通知重试放大外部限流。
  - 应对: 指数退避 + 最大重试上限 + 渠道级熔断（可选）。

## Acceptance Criteria (Phase 4)

- 关键写接口鉴权可配置启用，权限模型可测。
- 配置变更具备审计追踪与版本冲突保护。
- 相同幂等请求不会重复创建任务。
- `GET /api/v1/system/data-quality` 可用于日常巡检。
- 通知投递结果可追踪且失败不阻断主任务。
- CI 含质量门禁 + 迁移探针 + smoke，运行稳定。
- 全量门禁通过。
