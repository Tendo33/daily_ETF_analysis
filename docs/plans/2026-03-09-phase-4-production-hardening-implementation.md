# Phase 4 Production Hardening Implementation Plan (Optimized)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Phase 3 功能闭环完成后，将系统升级到可长期稳定运营的生产级状态：可观测、可扩展、可恢复、可审计、可安全发布。

**Architecture:** Phase 4 不再新增核心业务能力，重点做横切治理。保持现有模块边界不变，通过 `observability + reliability + ops` 三层增强实现“可运维系统”，并尽量以配置开关渐进启用，降低上线风险。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, pydantic-settings, GitHub Actions, Prometheus-compatible metrics (text format).

---

## Phase 4 前置条件

1. Phase 3 验收通过（history/backtest/notification/config/CI）。
2. 所有迁移已在测试环境验证可重复执行。
3. 关键写接口鉴权机制已可用（可开关）。

## Scope 与完成定义

- In Scope:
  - 运行时 SLI/SLO 与告警阈值。
  - 请求链路可追踪（request/task correlation）。
  - 数据生命周期治理（保留、归档、清理）。
  - 任务执行可靠性（超时、取消、重试上限、背压）。
  - 灾备能力（备份/恢复脚本 + 演练）。
  - 发布治理（质量门禁、迁移探针、smoke、回滚手册）。
  - 安全基线（依赖扫描、secret 检查、最小权限策略）。
- Out of Scope:
  - 新策略模型或新市场接入。
  - 前端控制台。
  - 分布式重构（如改造为 MQ/K8s 微服务架构）。
- Definition of Done:
  - 每个关键流程有可观测指标与告警阈值。
  - 故障可通过 runbook 快速定位和回滚。
  - 有可执行备份恢复流程，并有至少一次演练记录。
  - CI 能阻止高风险变更直接进入主分支。
  - 全量门禁通过并新增生产演练测试。

## SLO/SLI 目标（建议初始值）

- API 可用性（按 5 分钟窗口）：`>= 99.5%`
- 每日任务成功率（工作日）：`>= 98%`
- 单次分析任务 P95 时延：`<= 120s`（默认 ETF 清单规模）
- provider fallback 成功率：`>= 95%`
- 通知投递成功率（至少 1 渠道）：`>= 99%`

## Milestones（建议 2-3 周）

1. M1（D1-D2）：可观测指标与链路追踪。
2. M2（D3-D5）：任务可靠性与背压治理。
3. M3（D6-D8）：数据生命周期与存储治理。
4. M4（D9-D10）：备份恢复与演练自动化。
5. M5（D11-D13）：CI/CD 与发布回滚治理。
6. M6（D14-D16）：安全基线与依赖治理。
7. M7（D17-D18）：全链路演练与文档收敛。

## Task 1: 指标与追踪基线

**Files:**
- Create: `src/daily_etf_analysis/observability/metrics.py`
- Modify: `src/daily_etf_analysis/api/app.py`
- Modify: `src/daily_etf_analysis/services/task_manager.py`
- Test: `tests/test_metrics_endpoint.py`

**Step 1: Write the failing tests**
- `GET /api/metrics` 返回 text 指标。
- 指标至少覆盖：
  - `api_requests_total`
  - `analysis_task_total{status=...}`
  - `provider_calls_total{provider,operation,status}`
  - `notification_delivery_total{channel,status}`

**Step 2: Run test to verify it fails**
- Run: `uv run pytest tests/test_metrics_endpoint.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 增加请求中间件注入 `request_id`，并把 `task_id` 关联进日志。
- 暴露 `/api/metrics`（默认开启，可配置关闭）。

**Step 4: Run test to verify it passes**
- Run: `uv run pytest tests/test_metrics_endpoint.py -v`
- Expected: PASS

## Task 2: 任务可靠性与背压

**Files:**
- Modify: `src/daily_etf_analysis/services/task_manager.py`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_task_reliability.py`

**Step 1: Write the failing tests**
- 超过并发上限时返回明确错误或排队状态。
- 任务支持超时终止并记录失败原因。
- 同 symbol 重复运行在窗口期内被抑制（非幂等键语义）。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_task_reliability.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增配置：
  - `TASK_MAX_CONCURRENCY`
  - `TASK_TIMEOUT_SECONDS`
  - `TASK_DEDUP_WINDOW_SECONDS`
- task manager 实现超时与背压控制。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_task_reliability.py -v`
- Expected: PASS

## Task 3: 数据生命周期治理

**Files:**
- Create: `src/daily_etf_analysis/services/data_lifecycle_service.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Modify: `src/daily_etf_analysis/api/v1/router.py`
- Test: `tests/test_data_lifecycle.py`

**Step 1: Write the failing tests**
- 按保留策略清理过期任务/报告/报价。
- 清理前可 dry-run 预览影响行数。
- 清理结果写审计日志。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_data_lifecycle.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 新增配置：
  - `RETENTION_TASK_DAYS`
  - `RETENTION_REPORT_DAYS`
  - `RETENTION_QUOTE_DAYS`
- API：
  - `POST /api/v1/system/lifecycle/cleanup?dry_run=true|false`

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_data_lifecycle.py -v`
- Expected: PASS

## Task 4: 备份恢复与演练

**Files:**
- Create: `scripts/backup_db.py`
- Create: `scripts/restore_db.py`
- Create: `scripts/drill_recovery.py`
- Create: `tests/test_backup_restore_scripts.py`
- Modify: `README.md`

**Step 1: Write the failing tests**
- 备份脚本生成带时间戳文件。
- 恢复脚本可从备份恢复并通过基础一致性检查。
- 演练脚本输出 RTO/RPO 统计。

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_backup_restore_scripts.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 默认支持 SQLite 文件备份；数据库 URL 兼容扩展接口预留。
- 演练脚本不依赖外网。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_backup_restore_scripts.py -v`
- Expected: PASS

## Task 5: CI/CD 发布治理强化

**Files:**
- Modify: `.github/workflows/quality_gate.yml`
- Modify: `.github/workflows/daily_etf_analysis.yml`
- Create: `.github/workflows/release_guard.yml`
- Test: `tests/test_workflow_release_guard.py`

**Step 1: Write the failing tests/checks**
- workflow 包含：
  - 质量门禁
  - Alembic 迁移探针
  - smoke run
  - release guard（主分支前置条件）

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_workflow_release_guard.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- release guard 强制：
  - 所有 checks 通过
  - 版本号/变更日志一致性（若适用）
  - 可回滚指引链接

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_workflow_release_guard.py -v`
- Expected: PASS

## Task 6: 安全基线治理

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/security_scan.py`
- Create: `tests/test_security_scan_contract.py`
- Modify: `README.md`

**Step 1: Write the failing tests**
- 安全扫描脚本输出结构化结果：
  - `dependency_vulns`
  - `secret_leaks`
  - `policy_violations`

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_security_scan_contract.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 集成依赖审计与 secret 模式扫描（本地可运行）。
- CI 在 PR 上执行并可设阻断阈值。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_security_scan_contract.py -v`
- Expected: PASS

## Task 7: 运维 Runbook 与演练收口

**Files:**
- Create: `docs/operations/phase4-runbook.md`
- Modify: `docs/operations/phase3-runbook.md`（若存在）
- Create: `tests/test_runbook_links.py`

**Step 1: Write the failing tests**
- runbook 包含：
  - 告警分级
  - 常见故障定位流程
  - 回滚/恢复步骤
  - 值班检查清单

**Step 2: Run tests to verify they fail**
- Run: `uv run pytest tests/test_runbook_links.py -v`
- Expected: FAIL

**Step 3: Write minimal implementation**
- 将 API、脚本、workflow 与 runbook 建立双向链接。
- 所有命令可直接复制执行。

**Step 4: Run tests to verify they pass**
- Run: `uv run pytest tests/test_runbook_links.py -v`
- Expected: PASS

## 全量回归与交付

**Step 1: Run full quality gates**

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```

**Step 2: 生产模拟验证**
- `uv run pytest -m "integration or slow"`（如有）
- 运行一次备份恢复演练脚本并记录结果。

**Step 3: Commit in small batches**
- `feat: add phase4 metrics and tracing baseline`
- `feat: add task reliability controls and backpressure`
- `feat: add data lifecycle cleanup service`
- `feat: add backup restore drill scripts`
- `ci: add release guard and workflow hardening`
- `chore: add security baseline scan`
- `docs: add phase4 runbook`

## Task X: Market Review Depth Enhancements (Industry Trend/Risk/Weighted Recommendation)

**Goal:** 在保持简化架构的前提下，增强 ETF 大盘复盘深度，增加行业维度的趋势变化、风险聚合与推荐权重评分。

**Files:**
- Modify: `src/daily_etf_analysis/services/market_review.py`
- Modify: `src/daily_etf_analysis/repositories/repository.py`
- Modify: `src/daily_etf_analysis/reports/renderer.py`
- Modify: `templates/report_markdown.j2`
- Modify: `src/daily_etf_analysis/config/settings.py`
- Test: `tests/test_market_review.py`
- Test: `tests/test_report_renderer.py`

**Step 1: Write the failing tests**
- 行业趋势变化：近 N 天 action/trend 变化统计（per industry）。
- 行业风险聚合：按行业聚合风险提示（top N）。
- 行业推荐权重：action 分布 + 行业均分综合评分产出“推荐等级”。

**Step 2: Run tests to verify they fail**
- `uv run pytest tests/test_market_review.py -v`

**Step 3: Write minimal implementation**
- 新增配置：
  - `INDUSTRY_TREND_WINDOW_DAYS`（默认 5）
  - `INDUSTRY_RISK_TOP_N`（默认 3）
  - `INDUSTRY_RECOMMEND_WEIGHTS`（如 `{"buy":1,"hold":0,"sell":-1,"score_weight":0.5}`）
- 通过历史信号查询构建行业趋势变化统计。
- 风险提示按行业聚合，并截断 Top N。
- 计算行业推荐分：`action_score * (1-score_weight) + avg_score/100 * score_weight`。

**Step 4: Run tests to verify they pass**
- `uv run pytest tests/test_market_review.py -v`

## Risks & Mitigations

- 风险: 监控指标过多影响性能。
  - 应对: 先上核心指标，支持采样和分级开关。
- 风险: 背压策略导致任务堆积。
  - 应对: 增加排队长度告警与主动降载策略。
- 风险: 清理策略误删关键数据。
  - 应对: 默认 dry-run + 审计日志 + 分阶段执行。
- 风险: 安全扫描误报影响开发效率。
  - 应对: 设“阻断阈值 + 白名单机制 + 定期复核”。

## Acceptance Criteria (Phase 4)

- 具备可观测指标与请求/任务关联追踪。
- 任务执行具备并发、超时、背压治理能力。
- 数据清理具备 dry-run 与审计。
- 备份恢复脚本可用并完成至少一次演练。
- CI/CD 具备发布门禁与回滚治理。
- 安全扫描可在本地与 CI 执行。
- 全量门禁通过并形成可执行运维文档。
