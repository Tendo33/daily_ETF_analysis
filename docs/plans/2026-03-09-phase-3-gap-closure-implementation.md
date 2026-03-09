# Phase 3 Gap Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对齐 `daily_stock_analysis` 的高价值能力差距，在 ETF 场景补齐“历史查询 + 回测评估 + 多渠道通知 + 配置中心 + 每日 CI 强化”的产品闭环。

**Architecture:** 在现有 ETF 分层架构上继续增量扩展，不引入个股专属或 Agent 复杂能力。核心思路是先补“可追溯（history）”和“可验证（backtest）”，再补“可运营（notification/config/CI）”。所有新增能力通过 API 暴露，并保持现有分析任务链路兼容。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, httpx, APScheduler/GitHub Actions, lark-oapi, pydantic-settings.

---

## Gap Baseline (vs daily_stock_analysis)

- 已有（当前仓库/Phase 2 目标内）:
  - ETF 多市场分析任务、LLM fallback、Tavily 新闻、多源行情、基础任务 API、每日工作流基础版。
- 主要差距:
  - 缺少分析历史检索与详情 API（reference 有 `history list/detail/news`）。
  - 缺少回测闭环（reference 有 `backtest run/results/performance`）。
  - 通知仍偏单渠道（reference 已有多渠道通知矩阵与统一 sender）。
  - 缺少系统配置中心 API（reference 有 `config get/update/validate/schema`）。
  - 每日 CI 运行参数与运维可观测仍偏弱（reference 的 daily workflow 更成熟）。

## Scope

- In Scope:
  - ETF 历史分析 API（列表、详情、关联新闻、过滤/分页）。
  - ETF 信号回测引擎与回测 API（run/results/performance）。
  - 通知中心升级为多渠道插件化（Feishu/WeChat/Telegram/Email）。
  - 系统配置中心 API（读、校验、更新、热加载）。
  - 每日分析 CI 增强（模式、参数、探针日志、产物上传）。
- Out of Scope:
  - Agent 问答、策略 DSL、图片识别。
  - 前端 Web 管理台（仅保留 API）。
  - 股票个股级财报/基本面深度分析。

## Milestones (建议 2 周)

1. M1（D1-D2）：历史查询与报告详情 API。
2. M2（D3-D5）：回测引擎与回测 API。
3. M3（D6-D8）：通知中心多渠道插件化。
4. M4（D9-D10）：配置中心 API + 热加载。
5. M5（D11-D12）：每日 CI 增强 + 运维可观测。
6. M6（D13-D14）：联调、回归、文档收敛。

## Task 1: 扩展分析报告持久化契约（为 history/backtest 铺路）

**Files:**
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Modify: `alembic/versions/20260309_0001_initial.py`（或新增迁移）
- Create: `alembic/versions/20260309_0002_history_backtest_fields.py`
- Test: `tests/test_repository_reports_extended.py`

**Step 1: Write the failing test**
- 断言 `etf_analysis_reports` 能存取：
  - `query_id/report_type/context_snapshot/news_items_json/created_at`
- 断言可按 symbol/date/market 组合查询。

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_repository_reports_extended.py -v`
- Expected: FAIL（字段或方法缺失）

**Step 3: Write minimal implementation**
- 扩表并提供 repository 查询方法（分页 + 过滤）。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_repository_reports_extended.py -v`
- Expected: PASS

## Task 2: History API（列表/详情/新闻）

**Files:**
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_history_api.py`

**Step 1: Write the failing tests**
- `GET /api/v1/history?page=1&limit=20&symbol=US:QQQ`
- `GET /api/v1/history/{record_id}`
- `GET /api/v1/history/{record_id}/news`
- 覆盖 404/422 path。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_history_api.py -v`
- Expected: FAIL（端点不存在）

**Step 3: Write minimal implementation**
- service 层新增 `list_history/get_history_detail/get_history_news`。
- router 暴露 history 端点，返回标准化结构。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_history_api.py -v`
- Expected: PASS

## Task 3: ETF 回测引擎（基于已有信号记录）

**Files:**
- Create: `src/daily_etf_analysis/backtest/engine.py`
- Create: `src/daily_etf_analysis/backtest/models.py`
- Create: `src/daily_etf_analysis/repositories/backtest_repository.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Create: `alembic/versions/20260309_0003_backtest_tables.py`
- Test: `tests/test_backtest_engine.py`
- Test: `tests/test_backtest_repository.py`

**Step 1: Write the failing tests**
- 对历史分析结果执行回测，验证：
  - `direction_hit_rate`
  - `avg_return`
  - `max_drawdown`
  - `stop_loss_hit/take_profit_hit`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_backtest_engine.py tests/test_backtest_repository.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 回测对象使用 ETF 日线 + 分析动作映射（buy/hold/sell）。
- 支持窗口参数：`eval_window_days`, `min_age_days`, `force_recompute`。

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
- 封装 backtest service，router 返回分页结果和汇总指标。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_backtest_api.py -v`
- Expected: PASS

## Task 5: 通知中心插件化（多渠道）

**Files:**
- Create: `src/daily_etf_analysis/notifications/base.py`
- Modify: `src/daily_etf_analysis/notifications/feishu.py`
- Create: `src/daily_etf_analysis/notifications/wechat.py`
- Create: `src/daily_etf_analysis/notifications/telegram.py`
- Create: `src/daily_etf_analysis/notifications/email.py`
- Create: `src/daily_etf_analysis/notifications/manager.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_notification_manager.py`

**Step 1: Write the failing tests**
- 多渠道配置下，manager 会并发或顺序发送并汇总状态。
- 任一渠道失败不阻断其他渠道。
- 未配置渠道时返回 `disabled`。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_notification_manager.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 配置项建议：
  - `NOTIFY_CHANNELS=feishu,wechat,telegram,email`
  - `FEISHU_WEBHOOK_URL`
  - `WECHAT_WEBHOOK_URL`
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
  - `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECEIVERS`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_notification_manager.py -v`
- Expected: PASS

## Task 6: 报告渲染与发送编排

**Files:**
- Create: `src/daily_etf_analysis/reports/renderer.py`
- Modify: `scripts/run_daily_analysis.py`
- Modify: `src/daily_etf_analysis/services/task_manager.py`
- Test: `tests/test_report_renderer.py`
- Test: `tests/test_daily_runner_notify.py`

**Step 1: Write the failing tests**
- 渲染统一日报 markdown（summary + per-symbol details +风险提示）。
- 每日脚本完成后调用 notification manager 发送。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_report_renderer.py tests/test_daily_runner_notify.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 保存 `reports/report_YYYYMMDD.md` 与发送结果日志。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_report_renderer.py tests/test_daily_runner_notify.py -v`
- Expected: PASS

## Task 7: System Config API（参考 reference 的 schema/validate/update）

**Files:**
- Create: `src/daily_etf_analysis/services/system_config_service.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_system_config_api.py`

**Step 1: Write the failing tests**
- `GET /api/v1/system/config`
- `POST /api/v1/system/config/validate`
- `PUT /api/v1/system/config`
- `GET /api/v1/system/config/schema`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_system_config_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 支持脱敏返回、版本冲突检测、`reload_settings()` 热加载。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_system_config_api.py -v`
- Expected: PASS

## Task 8: GitHub 每日 CI v2（参数化 + 观测）

**Files:**
- Modify: `.github/workflows/daily_etf_analysis.yml`
- Modify: `scripts/run_daily_analysis.py`
- Modify: `README.md`
- Test: `tests/test_daily_runner_cli.py`

**Step 1: Write workflow/CLI failing tests**
- CLI 支持参数：
  - `--force-run`
  - `--symbols`
  - `--market`
  - `--skip-notify`
- workflow 输入映射到 CLI 参数。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_daily_runner_cli.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- workflow 增强项：
  - `schedule + workflow_dispatch`
  - 配置探针输出（只显示是否配置）
  - 上传 `reports/`、`logs/` artifact
  - 并发控制 `concurrency.group`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_daily_runner_cli.py -v`
- Expected: PASS

## Task 9: 文档与迁移说明收敛

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/operations/phase3-runbook.md`

**Step 1: Write doc checklist**
- 覆盖新增 API、配置、CI 变量、通知排障、回测解释口径。

**Step 2: Implement docs**
- 增加“从日报到回测”的操作路径。

**Step 3: Manual verify**
- Checklist 全部勾选。

## Task 10: 全量回归与提交

**Files:**
- Modify: `tests/`（所有新增测试）

**Step 1: Run full quality gates**

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```

**Step 2: Fix issues until clean**
- 门禁必须全绿。

**Step 3: Commit in small batches**
- `feat: add history APIs and report detail model`
- `feat: add etf backtest engine and APIs`
- `feat: add multi-channel notification manager`
- `feat: add system config APIs with validation`
- `ci: enhance daily etf analysis workflow`
- `docs: add phase3 runbook and config guides`

## Risks & Mitigations

- 风险: 回测结论与真实交易偏差大。
  - 应对: 在 API 与报告中明确“仅历史模拟，不构成投资建议”，并暴露假设参数。
- 风险: 多渠道通知失败率提升。
  - 应对: 发送结果逐渠道记录 + 重试 + 失败不阻断主流程。
- 风险: 配置中心误更新导致服务不可用。
  - 应对: validate-first + config_version 冲突保护 + 热加载失败回滚。
- 风险: CI secrets 不全导致定时任务失败。
  - 应对: workflow 启动时输出配置探针，缺失关键配置时 fail-fast。

## Acceptance Criteria (Phase 3)

- `history` 系列 API 可分页查询历史、拉取详情和新闻。
- `backtest` 系列 API 可运行回测并返回结果与 performance 汇总。
- 通知支持 `feishu/wechat/telegram/email` 多渠道，失败隔离。
- 存在 `system config` API（get/validate/update/schema）并支持热加载。
- 每日 CI 支持手动参数化触发，且产物可下载。
- 全量质量门禁通过。
