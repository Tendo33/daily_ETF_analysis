# daily_ETF_analysis

面向 A 股 / 港股 / 美股大盘 ETF 的智能分析系统。  
V1 目标是稳定产出结构化分析结果（不是只生成文案），并通过 API 提供任务查询与日报检索。

## 核心能力

- 三地市场 ETF 统一标识：`<MARKET>:<CODE>`，例如 `CN:159659`、`US:QQQ`、`HK:02800`
- 行情多源矩阵与优先级切换：`efinance -> akshare -> tushare/pytdx -> baostock -> yfinance`
- Provider 稳定性：统一 `retry + backoff + circuit breaker`，并暴露健康统计 API
- 新闻增强：Tavily（多 key、缓存、时效过滤）
- LLM 直接生成信号与摘要：`score/trend/action/confidence/risk_alerts/summary/key_points/model_used`
- 指数映射对比：按 `index_symbol + date` 输出跨市场 ETF 排序
- 任务化执行：`pending -> running -> completed | failed`
- 飞书通知（Webhook）与每日运行入口脚本
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

启动分析任务：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analysis/run \
  -H "Content-Type: application/json" \
  -d '{"symbols":["CN:159659","US:QQQ","HK:02800"],"force_refresh":false}'
```

查询任务列表：

```bash
curl http://127.0.0.1:8000/api/v1/analysis/tasks
```

查询单任务状态：

```bash
curl http://127.0.0.1:8000/api/v1/analysis/tasks/<task_id>
```

查询单 ETF 实时行情：

```bash
curl http://127.0.0.1:8000/api/v1/etfs/US:QQQ/quote
```

查询日报：

```bash
curl "http://127.0.0.1:8000/api/v1/reports/daily?date=2026-03-09&market=all"
```

查询指数映射对比：

```bash
curl "http://127.0.0.1:8000/api/v1/index-comparisons?index_symbol=NDX&date=2026-03-09"
```

查询 Provider 健康状态：

```bash
curl "http://127.0.0.1:8000/api/v1/system/provider-health"
```

## API 端点清单

- `POST /api/v1/analysis/run`
- `GET /api/v1/analysis/tasks`
- `GET /api/v1/analysis/tasks/{task_id}`
- `GET /api/v1/etfs`
- `PUT /api/v1/etfs`
- `GET /api/v1/index-mappings`
- `PUT /api/v1/index-mappings`
- `GET /api/v1/etfs/{symbol}/quote`
- `GET /api/v1/etfs/{symbol}/history?days=120`
- `GET /api/v1/reports/daily?date=YYYY-MM-DD&market=all|cn|hk|us`
- `GET /api/v1/index-comparisons?index_symbol=NDX&date=YYYY-MM-DD`
- `GET /api/v1/system/provider-health`
- `GET /api/health`

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
- 标准输出 JSON（包含 `task_id/status/report_path/notification_sent`）

## 飞书通知（Webhook）

配置：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
```

行为：
- 未配置时自动降级为禁用通知，不阻断任务。
- 网络失败时返回失败原因，不阻断日报产出。

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
