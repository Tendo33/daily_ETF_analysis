# Phase 2 Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成 Phase 2 增强目标：指数映射比较视图、交易日历/多时区调度增强、失败重试与熔断统计日志，并补齐多数据源矩阵（efinance/akshare/tushare/pytdx/baostock/yfinance）、飞书通知渠道、GitHub 每日分析 CI。

**Architecture:** 在现有 `api -> services -> repositories -> providers` 分层上做增量扩展。新增“跨市场对比查询”读模型；在 Provider Manager 上增加统一的 retry + circuit breaker 包装，并扩展到多源优先级矩阵；在 scheduler 与 observability 层补充时区与运行可观测能力。新增通知层（Feishu）与 `scripts + GitHub Actions` 的每日任务运行入口。保持现有 API 向后兼容。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, exchange-calendars, litellm, pytest, ruff, mypy.

---

## Scope 和完成定义

- In Scope:
  - 同指数跨市场 ETF 对比 API 与数据聚合逻辑。
  - 交易日与调度增强（按市场时区、市场开关、下次触发可观测）。
  - Provider 级重试、熔断、统计日志。
  - 数据源矩阵扩展与优先级接入：
    - Priority 0: `efinance>=0.5.5`
    - Priority 1: `akshare>=1.12.0`
    - Priority 2: `tushare>=1.4.0`, `pytdx>=1.72`
    - Priority 3: `baostock>=0.8.0`
    - Priority 4: `yfinance>=0.2.0`
  - 飞书通知渠道接入（`lark-oapi>=1.0.0` + Webhook / OpenAPI 配置）。
  - 对标 `daily_stock_analysis` 的 GitHub 每日分析工作流。
- Out of Scope:
  - 前端页面。
  - 新增外部新闻源（Bocha/Brave/SerpAPI）实现。
- Definition of Done:
  - 新增能力可通过 API 调用。
  - 数据源优先级可配置，且 fallback 顺序可观测。
  - 飞书通知可在任务完成后发送摘要（成功/失败都可观测）。
  - GitHub Actions 可定时与手动触发每日分析，并上传报告 artifact。
  - `uv run ruff check src tests scripts` 通过。
  - `uv run ruff format --check src tests scripts` 通过。
  - `uv run mypy src` 通过。
  - `uv run pytest` 通过。

## Milestones (建议 1 周)

1. M1（D1-D2）：指数映射对比能力（repository/service/api + tests）。
2. M2（D3-D4）：交易日历与调度增强（scheduler + tests）。
3. M3（D5-D6）：retry/circuit breaker 与 provider 统计。
4. M4（D7）：多数据源与飞书通知渠道接入。
5. M5（D8）：GitHub 每日分析 CI 接入与联调。
6. M6（D9-D10）：回归、文档更新、门禁收敛。

## Task 1: 指数映射比较数据契约

**Files:**
- Create: `src/daily_etf_analysis/domain/comparison.py`
- Modify: `src/daily_etf_analysis/domain/__init__.py`
- Test: `tests/test_index_comparison_contracts.py`

**Step 1: Write the failing test**
- 定义 `IndexComparisonRow` / `IndexComparisonResult` 的字段断言：
  - `index_symbol`, `report_date`, `rows[]`
  - 每行包含 `symbol`, `market`, `score`, `action`, `confidence`, `latest_price`, `change_pct`, `return_20`, `return_60`, `rank`

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_index_comparison_contracts.py -v`
- Expected: FAIL（模块不存在或字段缺失）

**Step 3: Write minimal implementation**
- 新建 comparison dataclass/pydantic model。
- 在 `domain/__init__.py` 导出。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_index_comparison_contracts.py -v`
- Expected: PASS

## Task 2: Repository 支持指数映射对比查询

**Files:**
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Test: `tests/test_repository_index_comparison.py`

**Step 1: Write the failing test**
- 构造 `index_proxy_mappings + etf_analysis_reports + quotes` 测试数据。
- 断言 repository 能返回按 `index_symbol` 过滤后的跨市场结果，并按 score 排序。

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_repository_index_comparison.py -v`
- Expected: FAIL（方法不存在）

**Step 3: Write minimal implementation**
- 在 `EtfRepository` 新增：
  - `get_index_proxy_symbols(index_symbol: str) -> list[str]`
  - `get_latest_reports_for_symbols(symbols: list[str], report_date: date | None)`
  - `get_latest_quotes_for_symbols(symbols: list[str])`

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_repository_index_comparison.py -v`
- Expected: PASS

## Task 3: Service 聚合指数映射比较

**Files:**
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Test: `tests/test_analysis_service_comparison.py`

**Step 1: Write the failing test**
- 断言 `get_index_comparison(index_symbol, date)`：
  - 会读取 mapping 下的 proxies。
  - 组合 report + quote + factors。
  - 输出包含 rank 且市场覆盖 CN/HK/US（如果有数据）。

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_analysis_service_comparison.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 在 service 中新增 `get_index_comparison`。
- 缺数据时返回空 rows，不抛异常。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_analysis_service_comparison.py -v`
- Expected: PASS

## Task 4: API 暴露指数映射比较视图

**Files:**
- Modify: `src/daily_etf_analysis/api/v1/schemas.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_api_v1_index_comparison.py`

**Step 1: Write the failing test**
- 新增 API 测试：
  - `GET /api/v1/index-comparisons?index_symbol=NDX&date=2026-03-09`
  - 参数错误 path（缺 index_symbol 或非法 date）断言 422。

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_api_v1_index_comparison.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 在 router 新增端点：
  - `GET /api/v1/index-comparisons`
- 在 schemas 增加 response model。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_api_v1_index_comparison.py -v`
- Expected: PASS

## Task 5: 交易日历与调度增强

**Files:**
- Modify: `src/daily_etf_analysis/core/trading_calendar.py`
- Modify: `src/daily_etf_analysis/scheduler/scheduler.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_trading_calendar.py`
- Test: `tests/test_scheduler.py`

**Step 1: Write the failing tests**
- 交易日历：
  - `is_market_open_today` 对市场和时区判断正确。
  - 新增 `next_market_session_date`（可选）行为测试。
- 调度：
  - `MARKETS_ENABLED` 生效，不在开启列表的市场不执行。
  - 同一分钟只触发一次（去重 marker）。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_trading_calendar.py tests/test_scheduler.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 调整 scheduler，仅对 enabled markets 调度。
- 统一使用市场时区时间窗口判断。
- 增加下次触发时间计算函数（用于日志/可观测）。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_trading_calendar.py tests/test_scheduler.py -v`
- Expected: PASS

## Task 6: Provider Retry + Circuit Breaker

**Files:**
- Create: `src/daily_etf_analysis/providers/resilience.py`
- Modify: `src/daily_etf_analysis/providers/market_data/base.py`
- Modify: `src/daily_etf_analysis/providers/news/manager.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_provider_resilience.py`
- Test: `tests/test_data_fetcher_manager.py`
- Test: `tests/test_news_manager_failover.py`

**Step 1: Write the failing tests**
- 验证失败后重试次数和退避行为。
- 连续失败触发熔断，熔断窗口期间快速失败。
- 半开后成功恢复 closed 状态。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_provider_resilience.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增 `RetryPolicy`, `CircuitBreaker`, `ProviderCallStats`。
- 在 market/news manager 的 provider 调用点接入 resilience wrapper。
- 配置新增：
  - `PROVIDER_MAX_RETRIES`
  - `PROVIDER_BACKOFF_MS`
  - `PROVIDER_CIRCUIT_FAIL_THRESHOLD`
  - `PROVIDER_CIRCUIT_RESET_SECONDS`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_provider_resilience.py tests/test_data_fetcher_manager.py tests/test_news_manager_failover.py -v`
- Expected: PASS

## Task 7: 统计日志与可观测接口

**Files:**
- Create: `src/daily_etf_analysis/observability/provider_stats.py`
- Modify: `src/daily_etf_analysis/services/analysis_service.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_provider_stats_api.py`

**Step 1: Write the failing test**
- 断言新增 API 返回 provider 级统计：
  - `success_count`, `failure_count`, `retry_count`, `circuit_state`, `last_error`

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_provider_stats_api.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增端点：`GET /api/v1/system/provider-health`
- 在 provider wrapper 中写入统计并输出结构化日志。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_provider_stats_api.py -v`
- Expected: PASS

## Task 8: 文档与配置更新

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `scripts/test_env.py`

**Step 1: Write doc validation checklist**
- Checklist:
  - 新 API 在 README 出现。
  - 新配置项在 `.env.example` 出现。
  - `test_env.py` 支持检查 resilience/scheduler 状态（最小版）。

**Step 2: Implement updates**
- 补充 Phase 2 新增能力说明和 cURL 示例。

**Step 3: Manual verify**
- 逐项对 checklist 打勾。

## Task 9: 全量回归与提交

**Files:**
- Modify: `tests/`（按上面任务新增）

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
- 推荐提交粒度：
  - `feat: add index comparison API and service`
  - `feat: add scheduler market gating and calendar enhancements`
  - `feat: add provider retry circuit breaker and stats`
  - `feat: add multi-source providers and priority config`
  - `feat: add feishu notification channel`
  - `ci: add daily etf analysis workflow`
  - `docs: update readme and env for phase2`

## Task 10: 多数据源矩阵接入（按优先级）

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Modify: `src/daily_etf_analysis/providers/market_data/base.py`
- Modify: `src/daily_etf_analysis/providers/market_data/__init__.py`
- Create: `src/daily_etf_analysis/providers/market_data/tushare_provider.py`
- Create: `src/daily_etf_analysis/providers/market_data/pytdx_provider.py`
- Create: `src/daily_etf_analysis/providers/market_data/baostock_provider.py`
- Modify: `.env.example`
- Test: `tests/test_data_fetcher_manager.py`

**Step 1: Write failing tests**
- 验证 `REALTIME_SOURCE_PRIORITY` 支持：
  - `efinance,akshare,tushare,pytdx,baostock,yfinance`
- 验证新增 provider 名称可被 manager 识别并参与 failover。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_data_fetcher_manager.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 增加依赖：
  - `tushare>=1.4.0`
  - `pytdx>=1.72`
  - `baostock>=0.8.0`
- 增加配置项（如 `TUSHARE_TOKEN`, `PYTDX_HOST`, `PYTDX_PORT`）。
- 新 provider 至少支持 CN ETF 日线读取；无实时能力时显式返回 `None`。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_data_fetcher_manager.py -v`
- Expected: PASS

## Task 11: 飞书通知渠道（Feishu）

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Create: `src/daily_etf_analysis/notifications/__init__.py`
- Create: `src/daily_etf_analysis/notifications/feishu.py`
- Create: `scripts/run_daily_analysis.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_feishu_notifier.py`

**Step 1: Write failing tests**
- 配置了 `FEISHU_WEBHOOK_URL` 时，通知发送函数能构造合法 payload。
- 未配置时，通知模块安全降级（不抛异常，返回 disabled 状态）。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_feishu_notifier.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 增加依赖：`lark-oapi>=1.0.0`
- 先落地 webhook 模式（OpenAPI 模式可作为后续扩展）。
- 在 daily run 脚本中，任务完成后发送摘要（包含日期、symbols、成功/失败数量）。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_feishu_notifier.py -v`
- Expected: PASS

## Task 12: GitHub 每日分析 CI（对标 daily_stock_analysis）

**Files:**
- Create: `.github/workflows/daily_etf_analysis.yml`
- Create/Modify: `scripts/run_daily_analysis.py`
- Modify: `README.md`

**Step 1: Write workflow validation checklist**
- Checklist:
  - 支持 `schedule`（工作日定时）与 `workflow_dispatch`（手动触发）。
  - 支持 `force_run` 输入（跳过交易日过滤）。
  - 支持 `symbols` 输入（可选定向分析）。
  - 上传 `reports/` 与 `logs/` artifact。
  - 支持 Feishu webhook 环境变量透传。

**Step 2: Implement workflow**
- 基于 `uv` 执行：
  - `uv sync --all-extras`
  - `uv run python scripts/run_daily_analysis.py ...`
- 参考 `daily_stock_analysis` 的并发与日志展示方式。

**Step 3: Manual verify**
- 本地使用 `act`（可选）或在 GitHub 手动触发 dry-run 验证。

## 风险与应对

- 风险: 重试与熔断导致调用时延变大。
  - 应对: 设置小而保守的默认值，支持配置覆盖。
- 风险: 日历库在部分环境不可用。
  - 应对: 保留降级逻辑并输出 warning 日志。
- 风险: 历史数据稀疏导致对比结果不完整。
  - 应对: 对空值显式返回 `null`，不抛异常。
- 风险: 新增数据源在 CI 环境不稳定或限流。
  - 应对: 以 `efinance/akshare` 为主链，其他源失败不阻断任务；日志记录 source failover。
- 风险: 飞书 webhook 配置错误导致通知失败。
  - 应对: 通知失败不影响分析主任务，单独记录 warning。
- 风险: GitHub Actions secrets 缺失导致每日任务失败。
  - 应对: workflow 启动阶段打印配置探针（仅显示是否配置，不打印密钥值）。

## 验收清单（Phase 2）

- `GET /api/v1/index-comparisons` 可用，并能返回跨市场对比行。
- 调度仅在 `MARKETS_ENABLED` 范围触发，且重复触发被抑制。
- Provider 失败时存在 retry，连续失败后熔断，恢复后可半开重试。
- `GET /api/v1/system/provider-health` 可返回统计状态。
- 已接入多数据源依赖与优先级配置：`efinance -> akshare -> tushare/pytdx -> baostock -> yfinance`。
- 飞书通知渠道可用（至少 webhook 模式）。
- 存在可运行的 GitHub 每日分析 workflow，且支持手动触发。
- 全量质量门禁通过。
