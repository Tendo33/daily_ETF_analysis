# daily_ETF_analysis

面向 A 股 / 港股 / 美股大盘 ETF 的智能分析系统。  
V1 目标是稳定产出结构化分析结果（不是只生成文案），并通过 API 提供 run 追踪、统一日报与建议历史检索。

## 核心能力

- 三地市场 ETF 统一标识：`<MARKET>:<CODE>`，例如 `CN:159659`、`US:QQQ`、`HK:02800`
- 行情多源矩阵与优先级切换：`efinance -> akshare -> tushare/pytdx -> baostock -> yfinance`
- Provider 稳定性：统一 `retry + backoff + circuit breaker`，并暴露健康统计 API
- 可观测性基线：`/api/metrics`（Prometheus text 格式）
- 新闻增强：Tavily（多 key、缓存、时效过滤）
- LLM 直接生成信号与摘要：`score/trend/action/confidence/risk_alerts/summary/key_points/model_used`
- 指数映射对比：按 `index_symbol + date` 输出跨市场 ETF 排序
- 历史追溯：`history/signals` 按 run/symbol/date 可筛选查询
- 回测能力：`backtest` 运行与 run/symbol 双层绩效
- 系统配置中心：`get/validate/update/schema/audit`（支持版本检查）
- 任务化执行：`pending -> processing -> completed | failed`
- 通知中心（feishu/wechat/telegram/email）与每日运行入口脚本
- 持久化：SQLite + SQLAlchemy + Alembic

## 项目结构

```text
src/daily_etf_analysis/
├── api/               # FastAPI 路由
├── config/            # Settings 与配置优先级解析
├── core/              # 交易日判断
├── domain/            # ETF 领域模型与 symbol 规范
├── llm/               # EtfAnalyzer（LiteLLM Router + fallback）
├── pipelines/         # DailyPipeline 编排
├── providers/         # 行情/新闻 Provider
├── repositories/      # 数据库读写
├── scheduler/         # 定时调度
└── services/          # TaskManager / AnalysisService / 因子计算
```

## 快速开始

1. 安装依赖

```bash
uv sync --all-extras
```

2. 准备环境变量

```bash
cp .env.example .env
```

3. 最小必填配置（建议先保证可跑通）

```env
ETF_LIST=CN:159659,US:QQQ,HK:02800
INDEX_PROXY_MAP={"NDX":["US:QQQ","CN:159659"],"HSI":["HK:02800","CN:159920"]}
DATABASE_URL=sqlite:///./data/daily_etf_analysis.db
LLM_CHANNELS=aihubmix
LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1
LLM_AIHUBMIX_API_KEY=sk-xxxx
LLM_AIHUBMIX_MODELS=gpt-4o-mini
TAVILY_API_KEYS=tvly-xxxx
```

兼容说明：`TASK_QUEUE_MAX_SIZE` 与 `TASK_DEDUP_WINDOW_SECONDS` 当前仅保留配置键，运行时不再驱动队列策略（使用活跃任务去重）。

4. 启动 API

```bash
uv run uvicorn daily_etf_analysis.api.app:app --host 0.0.0.0 --port 8000
```

5. 验证服务

```bash
curl http://127.0.0.1:8000/api/health
```

OpenAPI 文档：
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

## 数据源优先级（Phase 2）

默认 `REALTIME_SOURCE_PRIORITY`：

```env
REALTIME_SOURCE_PRIORITY=efinance,akshare,tushare,pytdx,baostock,yfinance
```

- `efinance`（Priority 0）
- `akshare`（Priority 1）
- `tushare` / `pytdx`（Priority 2）
- `baostock`（Priority 3）
- `yfinance`（Priority 4，US 主源 + fallback）

## LLM 配置优先级

当前实现采用三层优先级（由高到低）：

1. `LITELLM_CONFIG`（YAML `model_list`）
2. `LLM_CHANNELS`（渠道模式）
3. legacy keys（`OPENAI_*`, `GEMINI_*`, `ANTHROPIC_*`, `DEEPSEEK_*`）

当主模型失败时，会按 fallback 列表继续尝试；全失败时返回中性降级结果：
- `success=false`
- `score=50`
- `trend=neutral`
- `action=hold`

## API 快速示例

创建一次分析运行（run）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analysis/runs \
  -H "Content-Type: application/json" \
  -d '{"symbols":["CN:159659","US:QQQ","HK:02800"],"force_refresh":false}'
```

返回 `202 Accepted`，包含 `run_id` 与初始 `status`。

查询运行状态：

```bash
curl http://127.0.0.1:8000/api/v1/analysis/runs/<run_id>
```

查询统一日报契约：

```bash
curl "http://127.0.0.1:8000/api/v1/reports/daily?date=2026-03-09&market=all&run_id=<run_id>"
```

查询建议历史（signals）：

```bash
curl "http://127.0.0.1:8000/api/v1/history/signals?symbol=US:QQQ&run_id=<run_id>"
```

查询单 ETF 实时行情：

```bash
curl http://127.0.0.1:8000/api/v1/etfs/US:QQQ/quote
```

查询指数映射对比：

```bash
curl "http://127.0.0.1:8000/api/v1/index-comparisons?index_symbol=NDX&date=2026-03-09"
```

查询 Provider 健康状态：

```bash
curl "http://127.0.0.1:8000/api/v1/system/provider-health"
```

查询系统指标：

```bash
curl "http://127.0.0.1:8000/api/metrics"
```

运行回测：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbols":["US:QQQ"],"eval_window_days":20}'
```

查询系统配置：

```bash
curl "http://127.0.0.1:8000/api/v1/system/config"
```

生命周期清理（默认 dry-run）：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/system/lifecycle/cleanup?dry_run=true"
```

## API 端点清单

- `POST /api/v1/analysis/runs`
- `GET /api/v1/analysis/runs/{run_id}`
- `GET /api/v1/reports/daily?date=YYYY-MM-DD&market=all|cn|hk|us&run_id=<run_id>`
- `GET /api/v1/history/signals?symbol=US:QQQ&run_id=<run_id>&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&limit=200`
- `GET /api/v1/etfs`
- `PUT /api/v1/etfs`
- `GET /api/v1/index-mappings`
- `PUT /api/v1/index-mappings`
- `GET /api/v1/etfs/{symbol}/quote`
- `GET /api/v1/etfs/{symbol}/history?days=120`
- `POST /api/v1/backtest/run`
- `GET /api/v1/backtest/results?run_id=<run_id>`
- `GET /api/v1/backtest/performance?run_id=<run_id>`
- `GET /api/v1/backtest/performance/{symbol}?run_id=<run_id>`
- `GET /api/v1/index-comparisons?index_symbol=NDX&date=YYYY-MM-DD`
- `GET /api/v1/system/provider-health`
- `GET /api/v1/system/config`
- `POST /api/v1/system/config/validate`
- `PUT /api/v1/system/config`
- `GET /api/v1/system/config/schema`
- `GET /api/v1/system/config/audit`
- `POST /api/v1/system/lifecycle/cleanup?dry_run=true|false`
- `GET /api/health`
- `GET /api/metrics`

## 数据库与迁移

- 默认使用 SQLite，路径来自 `DATABASE_URL`（默认 `./data/daily_etf_analysis.db`）
- 代码首次运行会自动建表（`SQLAlchemy metadata.create_all`）
- 若你希望按迁移管理 schema，可使用 Alembic：

```bash
uv run alembic upgrade head
```

## 配置检查与连通性自检

```bash
uv run python scripts/test_env.py --config
uv run python scripts/test_env.py --fetch --symbol CN:159659
uv run python scripts/test_env.py --llm
```

## 每日运行脚本（Phase 2）

```bash
uv run python scripts/run_daily_analysis.py
```

常用参数：

```bash
uv run python scripts/run_daily_analysis.py --force-run --market cn
uv run python scripts/run_daily_analysis.py --symbols CN:159659,US:QQQ --skip-notify
```

输出：
- `reports/daily_etf_<date>_<taskid>.json`
- `reports/report_YYYYMMDD_<taskid8>.md`
- `reports/report_YYYYMMDD.md`（兼容旧路径，最新一次运行会覆盖）
- 标准输出 JSON（包含 `task_id/task_ids/status/report_path/markdown_report_path/notification_sent/notification_channels`）

## 通知中心（Phase 3）

配置：

```env
NOTIFY_CHANNELS=feishu,wechat,telegram,email
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
WECHAT_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_SMTP_HOST=
EMAIL_SMTP_PORT=25
EMAIL_FROM=
EMAIL_TO=
```

行为：
- 未配置渠道返回 `disabled`，不阻断任务。
- 单渠道失败不阻断其他渠道发送。
- 输出包含 `notification_channels` 聚合结果。

## API 写接口鉴权（Phase 3）

```env
API_AUTH_ENABLED=true
API_ADMIN_TOKEN=replace-with-strong-token
```

- 当 `API_AUTH_ENABLED=false`（默认）时，兼容旧行为。
- 当启用后，所有写接口（`POST/PUT`）需 `Authorization: Bearer <API_ADMIN_TOKEN>`。

## GitHub 每日分析 CI（Phase 2）

工作流文件：`.github/workflows/daily_etf_analysis.yml`

- 定时：工作日 UTC 13:00（北京时间 21:00）
- 手动触发参数：`force_run`、`symbols`、`market`、`skip_notify`
- 并发组控制：避免同类任务重入
- 产物上传：`reports/`、`logs/`
- 配置探针：只输出“是否配置”，不泄露密钥

## 定时任务说明

- 调度器配置字段：`SCHEDULE_ENABLED`, `SCHEDULE_CRON_CN/HK/US`
- 当前默认不自动启动（`SCHEDULE_ENABLED=false`）
- 若需要常驻调度，建议在单独进程中初始化 `EtfScheduler` 并调用 `start()`

## 质量门禁

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest
```

## 当前默认与边界

- 默认数据库：SQLite
- 默认新闻源：Tavily（其他新闻源接口已预留）
- V1 不含前端界面，仅提供 FastAPI + JSON 报告接口
- 部分时间字段仍使用 `datetime.utcnow()`，测试会出现 deprecation warning（不影响运行）

## 运维 Runbook

- Phase 3 运维手册：`docs/operations/phase3-runbook.md`
- Phase 4 运维手册：`docs/operations/phase4-runbook.md`

## Phase 4 备份与安全脚本

```bash
uv run python scripts/backup_db.py --output-dir backups
uv run python scripts/restore_db.py --backup-file backups/<backup>.db
uv run python scripts/drill_recovery.py --backup-dir backups
uv run python scripts/security_scan.py
```
