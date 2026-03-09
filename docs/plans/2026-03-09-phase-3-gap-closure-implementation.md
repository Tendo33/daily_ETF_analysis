# Phase 3 Gap Closure Implementation Plan (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在当前 Phase 2 基础上，补齐产品闭环能力：`history` 可追溯、`backtest` 可验证、`notification` 可运营、`system-config` 可治理、`daily CI` 可稳定运维。

**Architecture:** 继续采用现有 `api -> services -> repositories -> providers` 分层。Phase 3 只做增量扩展，不改变现有分析任务主链路。新增能力通过独立 service/repository 模块接入，避免把 `TaskManager` 膨胀成“万能编排器”。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, pydantic-settings, httpx, GitHub Actions.

---

## 执行前约束（必须满足）

1. 只允许新增前向 Alembic 迁移，禁止改写历史迁移文件。
2. 所有新增写接口必须接入统一鉴权依赖（可配置开关，默认兼容关闭）。
3. 现有 API 保持向后兼容；字段新增优先可选。
4. 每个任务必须遵守 TDD：先红后绿。
5. 每个 Milestone 必须通过质量门禁后再进入下一阶段。

## Gap Baseline（基于当前仓库）

- 已有:
  - 分析任务 API、指数对比 API、provider 健康 API。
  - 多源行情 + retry/circuit breaker。
  - 单渠道飞书通知与每日脚本/CI 基础版。
- 缺口:
  - 缺少 `history` 列表/详情/关联新闻 API。
  - 缺少回测能力与回测 API。
  - 缺少通知中心（多渠道统一管理）。
  - 缺少配置中心 API（持久化、校验、审计）。
  - daily workflow 缺少更强治理与参数契约测试。

## Scope 与完成定义

- In Scope:
  - history API（分页列表、详情、关联新闻）。
  - 回测引擎 + backtest API。
  - 通知中心插件化（feishu/wechat/telegram/email）。
  - system config API（get/validate/update/schema）+ 审计日志。
  - daily CI v2（参数契约、探针、产物、并发治理）。
- Out of Scope:
  - 前端管理台。
  - 策略 DSL 与复杂 agent 能力。
  - 股票个股深度基本面功能。
- Definition of Done:
  - 新 API 可用并有测试覆盖。
  - 新迁移可重复执行，`alembic upgrade head` 成功。
  - 写接口在 `API_AUTH_ENABLED=true` 时强制鉴权。
  - 全量门禁通过：ruff/format/mypy/pytest。

## Milestones（建议 2 周）

1. M1（D1-D2）：schema 扩展 + history API。
2. M2（D3-D5）：backtest 引擎 + API。
3. M3（D6-D8）：通知中心插件化 + 日报渲染发送。
4. M4（D9-D10）：system config API + 审计/热加载。
5. M5（D11-D12）：CI v2 强化与契约测试。
6. M6（D13-D14）：全量回归与文档收敛。

## Task 1: 数据契约与迁移基线（history/backtest/config 审计）

**Files:**
- Create: `alembic/versions/20260309_0004_phase3_core_tables.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Test: `tests/test_repository_phase3_schema.py`

**Step 1: Write the failing tests**
- 断言新增表/字段可写可读：
  - `etf_analysis_reports`: `context_snapshot_json`, `news_items_json`, `created_at`
  - `backtest_runs`, `backtest_results`
  - `system_config_audit_logs`

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_repository_phase3_schema.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增迁移与 repository 对应 CRUD。
- 明确索引：`symbol + trade_date`、`run_id`、`config_version`。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_repository_phase3_schema.py -v`
- Expected: PASS

## Task 2: History API（list/detail/news）

**Files:**
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_history_api.py`

**Step 1: Write the failing tests**
- `GET /api/v1/history?page=1&limit=20&symbol=US:QQQ`
- `GET /api/v1/history/{record_id}`
- `GET /api/v1/history/{record_id}/news`
- 覆盖 `404/422`。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_history_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- service 新增 `list_history/get_history_detail/get_history_news`。
- 默认分页参数：`page=1`, `limit=20`, `limit<=200`。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_history_api.py -v`
- Expected: PASS

## Task 3: Backtest 引擎与持久化

**Files:**
- Create: `src/daily_etf_analysis/backtest/models.py`
- Create: `src/daily_etf_analysis/backtest/engine.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Test: `tests/test_backtest_engine.py`
- Test: `tests/test_backtest_repository.py`

**Step 1: Write the failing tests**
- 输入历史信号与价格序列，输出：
  - `direction_hit_rate`
  - `avg_return`
  - `max_drawdown`
  - `win_rate`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_backtest_engine.py tests/test_backtest_repository.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 行为口径固定：
  - `buy=+1`, `hold=0`, `sell=-1`
  - `eval_window_days` 默认 20
  - 无足够未来数据则跳过该样本并统计 `skipped_count`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_backtest_engine.py tests/test_backtest_repository.py -v`
- Expected: PASS

## Task 4: Backtest API（run/results/performance）

**Files:**
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Test: `tests/test_backtest_api.py`

**Step 1: Write the failing tests**
- `POST /api/v1/backtest/run`
- `GET /api/v1/backtest/results`
- `GET /api/v1/backtest/performance`
- `GET /api/v1/backtest/performance/{symbol}`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_backtest_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- API 返回 run-level 汇总和 symbol-level 指标。
- 错误输入返回 422，不存在 run_id 返回 404。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_backtest_api.py -v`
- Expected: PASS

## Task 5: 通知中心插件化（不破坏现有 Feishu 路径）

**Files:**
- Create: `src/daily_etf_analysis/notifications/base.py`
- Create: `src/daily_etf_analysis/notifications/manager.py`
- Create: `src/daily_etf_analysis/notifications/wechat.py`
- Create: `src/daily_etf_analysis/notifications/telegram.py`
- Create: `src/daily_etf_analysis/notifications/email.py`
- Modify: `src/daily_etf_analysis/notifications/feishu.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_notification_manager.py`

**Step 1: Write the failing tests**
- 多渠道发送结果聚合。
- 单渠道失败不阻断其他渠道。
- 未配置渠道返回 `disabled`。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_notification_manager.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增配置：
  - `NOTIFY_CHANNELS=feishu,wechat,telegram,email`
  - 各渠道凭证字段（按需）
- `run_daily_analysis.py` 改为调用 `NotificationManager`。
- 不改 `TaskManager` 职责。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_notification_manager.py -v`
- Expected: PASS

## Task 6: 报告渲染模块化

**Files:**
- Create: `src/daily_etf_analysis/reports/renderer.py`
- Modify: `src/daily_etf_analysis/cli/run_daily_analysis.py`
- Test: `tests/test_report_renderer.py`
- Test: `tests/test_daily_runner_notify.py`

**Step 1: Write the failing tests**
- 日报 markdown 渲染结构固定：
  - summary
  - top symbols
  - risk alerts

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_report_renderer.py tests/test_daily_runner_notify.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- runner 复用 renderer 产出 markdown，并复用 NotificationManager 发送。
- 输出 `reports/report_YYYYMMDD.md`。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_report_renderer.py tests/test_daily_runner_notify.py -v`
- Expected: PASS

## Task 7: System Config API（持久化 + 审计 + 鉴权）

**Files:**
- Create: `src/daily_etf_analysis/services/system_config_service.py`
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_system_config_api.py`

**Step 1: Write the failing tests**
- `GET /api/v1/system/config`
- `POST /api/v1/system/config/validate`
- `PUT /api/v1/system/config`
- `GET /api/v1/system/config/schema`
- `GET /api/v1/system/config/audit`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_system_config_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 更新流程：`validate -> optimistic version check -> persist -> audit log -> reload_settings`。
- `PUT` 仅允许 admin token（当 auth 开启时）。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_system_config_api.py -v`
- Expected: PASS

## Task 8: Daily CI v2（契约化与探针）

**Files:**
- Modify: `.github/workflows/daily_etf_analysis.yml`
- Modify: `README.md`
- Test: `tests/test_daily_workflow_contracts.py`

**Step 1: Write the failing tests/checks**
- 校验 workflow 保留并正确映射：
  - `force_run/symbols/market/skip_notify`
  - `concurrency.group`
  - artifact upload
  - config probe（不泄露 secret）

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_daily_workflow_contracts.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 仅补缺失治理，不重复实现已有功能。
- 增加 daily runner smoke（`--skip-notify`）。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_daily_workflow_contracts.py -v`
- Expected: PASS

## Task 9: 文档与运维说明收敛

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/operations/phase3-runbook.md`

**Step 1: Write doc checklist**
- 新 API、配置项、鉴权开关、回测口径、通知排障。

**Step 2: Implement docs**
- 增加“从 analysis -> history -> backtest -> notify”的操作路径。

**Step 3: Manual verify**
- Checklist 全部勾选。

## Task 10: 全量回归与提交

**Files:**
- Modify: `tests/`（按任务新增/调整）

**Step 1: Run full quality gates**

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```

**Step 2: Fix issues until clean**
- 门禁全部通过后才能进入提交步骤。

**Step 3: Commit in small batches**
- `feat: add phase3 history api and repository support`
- `feat: add phase3 backtest engine and apis`
- `feat: add notification manager and report renderer`
- `feat: add system config api with audit and auth gate`
- `ci: upgrade daily workflow contracts and probes`
- `docs: add phase3 runbook and config docs`

## Risks & Mitigations

- 风险: 回测被误解为投资建议。
  - 应对: API 与报告强制免责声明 + 口径字段显式返回。
- 风险: 多渠道通知引入不稳定依赖。
  - 应对: 渠道隔离、失败不阻断主流程、统一投递结果日志。
- 风险: 配置热加载失败导致运行时异常。
  - 应对: 先校验再持久化，reload 失败回滚版本。
- 风险: 鉴权开启后历史脚本受影响。
  - 应对: 默认关闭；runbook 提供切换与回退步骤。

## Acceptance Criteria (Phase 3)

- `history` API 可分页检索、查看详情、查看关联新闻。
- `backtest` API 可运行并返回 run/symbol 两层指标。
- 通知支持多渠道统一管理，失败隔离。
- `system config` API 支持 get/validate/update/schema/audit。
- 写接口鉴权在开关开启时生效。
- 仅新增前向迁移，历史迁移文件无改动。
- 全量质量门禁通过。
