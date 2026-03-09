# daily_ETF_analysis 设计方案（对标 daily_stock_analysis）

日期：2026-03-09  
目标仓库：`/Users/simonsun/github_project/daily_ETF_analysis`  
参考仓库：`/Users/simonsun/github_project/daily_ETF_analysis/.reference/daily_stock_analysis`

## 1. 目标与范围

### 1.1 业务目标
- 仅聚焦「大盘 ETF」分析，不做个股深度基本面。
- 覆盖三地市场：A 股、港股、美股。
- 支持“同一指数跨市场映射”分析，例如：
  - 美股指数：`IXIC`（纳斯达克综合）/ `NDX`（纳指100）
  - 美股 ETF：`QQQ`
  - A 股映射 ETF：如 `159659`（由用户维护映射清单）

### 1.2 非目标（V1 不做）
- 图片识别加自选（参考项目的 Vision 入口可后续再接）。
- 多轮 Agent 策略问答。
- 复杂回测引擎（先保留简化版验证）。

## 2. 从参考仓库抽取的可复用设计

参考仓库的核心值得复用，不建议全量照搬：

1. `DataFetcherManager` 多数据源优先级 + 失败自动切换。
2. `trading_calendar` 按市场时区判断交易日（cn/hk/us）。
3. 分层结构：`api -> service -> repository -> data_provider`。
4. 异步任务队列与任务状态查询接口（避免单次分析阻塞）。
5. 配置中心化（`.env` + config dataclass/pydantic）与可观测日志。

建议简化的点：

1. 去掉与 ETF 无关的大量能力（如个股特定策略、复杂 Bot 模式）。
2. 先做规则引擎报告，再按需接 LLM 文案增强。

## 3. ETF 域模型设计

## 3.1 代码规范（统一 Symbol）
- 统一内部格式：`<market>:<code>`
  - `CN:159659`
  - `HK:02800`
  - `US:QQQ`
  - `INDEX:NDX`

## 3.2 指数映射表（核心）
- 新增配置 `INDEX_PROXY_MAP`（JSON）：
  - `NDX -> ["US:QQQ", "CN:159659"]`
  - `SPX -> ["US:SPY", "CN:513500"]`
  - `HSI -> ["HK:02800", "CN:159920"]`
- 说明：映射数据业务上会变动，必须配置化，不应写死在代码。

## 3.3 核心实体
- `EtfInstrument`：市场、代码、名称、跟踪指数、币种、是否启用。
- `EtfDailyBar`：OHLCV、涨跌幅、数据源、交易日。
- `EtfRealtimeQuote`：最新价、涨跌幅、成交额、更新时间、数据源。
- `EtfSignal`：趋势标签、风险等级、打分、建议动作。
- `EtfReport`：单 ETF 分析结果 + 当日汇总。

## 4. 需要请求的接口（外部依赖）

## 4.1 行情数据接口（优先级顺序）

### A 股 / 港股 ETF（主）
1. `efinance`
  - 历史：`ef.stock.get_quote_history`
  - 实时：`ef.stock.get_realtime_quotes`
2. `akshare`
  - A 股 ETF 日线：`ak.fund_etf_hist_em`
  - A 股 ETF 实时：`ak.fund_etf_spot_em`
  - 港股日线：`ak.stock_hk_hist`
  - 港股实时：`ak.stock_hk_spot_em`

### 美股 ETF（主）
1. `yfinance`
  - 日线：`yf.download`
  - 实时近似：`Ticker.history(period='1d'/'2d')`

### 备用源（可选）
1. `tushare`（有 token 时）
  - ETF 日线：`fund_daily`
  - ETF 基础信息：`fund_basic`

## 4.2 交易日历
1. `exchange-calendars`
  - `XSHG` / `XHKG` / `XNYS`
  - 用于“当日是否执行某市场分析”的过滤。

## 4.3 新闻接口（推荐默认）
1. `Tavily`（推荐主搜索源）
2. `Bocha`
3. `Brave`
4. `SerpAPI`

用途：只提取 ETF 对应指数的当日宏观/板块新闻，避免个股噪音。

### Tavily 接入建议（V1 就接）
- 环境变量：`TAVILY_API_KEYS`（支持多 key，逗号分隔）。
- 调用方式：`search_depth="advanced"`，限制最近 `1-3` 天新闻。
- 输出字段：`title`、`url`、`content/snippet`、`published_date`。
- 工程策略：失败重试（指数退避）+ key 轮询 + 本地短时缓存（10~30 分钟）。
- 降级链路：`Tavily -> Bocha -> Brave -> SerpAPI`。

## 4.4 LLM 接口（可选增强）
1. OpenAI 兼容（或 LiteLLM 统一路由）
2. Gemini / Claude（可后续接）

用途：把规则引擎结果转成更自然的日报文案，不参与核心信号决策。

## 5. 项目架构（daily_ETF_analysis）

建议在现有模板基础上扩展为以下结构：

```text
src/daily_etf_analysis/
├── api/                       # FastAPI 路由层
│   └── v1/
├── services/                  # 用例编排（分析任务、报告生成）
├── repositories/              # DB 读写（SQLite/Postgres）
├── providers/                 # 外部接口适配（akshare/efinance/yfinance）
│   ├── market_data/
│   ├── news/
│   └── llm/
├── domain/                    # 领域模型与规则（ETF/Signal）
├── pipelines/                 # 每日分析流水线
├── scheduler/                 # 定时任务
├── config/                    # Settings（pydantic）
└── observability/             # 日志、指标、trace-id
```

分层原则：
- `api` 只做参数校验与响应转换。
- `services` 负责业务编排。
- `providers` 负责外部调用细节与重试。
- `repositories` 只做持久化，禁止写业务逻辑。

## 6. 分析流水线设计

每日任务（按市场并行）：

1. 加载 ETF 清单与指数映射。
2. 交易日判断（cn/hk/us），非交易日跳过对应市场。
3. 获取日线 + 实时行情（带数据源 failover）。
4. 计算因子：
  - 趋势：MA5/10/20、MA20 斜率
  - 动量：20 日、60 日收益
  - 波动：ATR 或滚动波动率
  - 回撤：近 60 日最大回撤
  - 量能：量比/成交额分位（可用时）
5. 规则打分：
  - `score >= 70`：偏多
  - `40 <= score < 70`：中性
  - `< 40`：防守
6. 生成结构化结果（JSON）并持久化。
7. 输出：
  - 控制台/文件日报（V1）
  - API 拉取（V1）
  - webhook 推送（V2）

## 7. API 设计（建议先做这些）

## 7.1 分析任务
- `POST /api/v1/analysis/run`
  - 入参：`symbols[] | groups[] | force_refresh`
  - 出参：`task_id`
- `GET /api/v1/analysis/tasks`
- `GET /api/v1/analysis/tasks/{task_id}`

## 7.2 ETF 管理
- `GET /api/v1/etfs`：返回当前监控 ETF 清单
- `PUT /api/v1/etfs`：批量覆盖或更新清单
- `GET /api/v1/index-mappings`：指数与跨市场 ETF 映射
- `PUT /api/v1/index-mappings`

## 7.3 行情与报告
- `GET /api/v1/etfs/{symbol}/quote`
- `GET /api/v1/etfs/{symbol}/history?days=120`
- `GET /api/v1/reports/daily?date=YYYY-MM-DD&market=cn|hk|us|all`
- `GET /api/health`

## 8. 存储设计（SQLite 起步）

建议表结构：

1. `etf_instruments`
  - `symbol(pk)`, `market`, `code`, `name`, `benchmark_index`, `enabled`, `updated_at`
2. `index_proxy_mappings`
  - `index_symbol`, `proxy_symbol`, `priority`
3. `etf_daily_bars`
  - `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `amount`, `source`
  - 唯一键：`(symbol, trade_date)`
4. `etf_realtime_quotes`
  - `symbol`, `quote_time`, `price`, `change_pct`, `turnover`, `source`
5. `analysis_tasks`
  - `task_id`, `status`, `params_json`, `started_at`, `finished_at`, `error`
6. `etf_analysis_reports`
  - `task_id`, `trade_date`, `symbol`, `signal`, `score`, `factors_json`, `report_json`

## 9. 配置项（.env）建议

- `ETF_LIST`：`CN:159659,US:QQQ,HK:02800`
- `INDEX_PROXY_MAP`：JSON 字符串
- `MARKETS_ENABLED`：`cn,hk,us`
- `REALTIME_SOURCE_PRIORITY`：`efinance,akshare_em,akshare_sina,yfinance`
- `ENABLE_NEWS`：`true/false`
- `TAVILY_API_KEYS`：Tavily 密钥（多个 key 用逗号分隔）
- `NEWS_PROVIDER_PRIORITY`：`tavily,bocha,brave,serpapi`
- `ENABLE_LLM_SUMMARY`：`true/false`
- `SCHEDULE_ENABLED`、`SCHEDULE_CRON_CN`、`SCHEDULE_CRON_US`、`SCHEDULE_CRON_HK`
- `DATABASE_URL`（默认 sqlite）

## 10. 分阶段落地计划

### Phase 1（MVP，1-2 周）
- 完成 ETF 清单管理 + 数据抓取 + 指标计算 + 日报 JSON 输出。
- 完成 FastAPI 基础接口（health、run、task、quote、history）。

### Phase 2（增强，1 周）
- 增加指数映射比较视图（同指数跨市场 ETF 对比）。
- 增加交易日历过滤、多市场时区调度。
- 增加失败重试与熔断统计日志。

### Phase 3（可选）
- 接新闻搜索与 LLM 摘要。
- 接 webhook 推送（企微/飞书/Telegram）。

## 11. 技术风险与规避

1. 免费数据源限流/变更频繁  
   - 规避：多源优先级 + 熔断 + 缓存 + force refresh 开关。

2. 跨市场时区导致“交易日误判”  
   - 规避：严格按 market timezone 判断当日。

3. 指数映射长期维护成本  
   - 规避：配置化 + API 可维护，不写死在代码。

4. LLM 输出不稳定  
   - 规避：信号先规则化，LLM 只做文本润色。

## 12. 与你当前仓库的直接对接建议

现仓库是模板骨架，建议先新增以下最小模块：

1. `src/daily_etf_analysis/providers/market_data/`（先接 `yfinance + akshare`）
2. `src/daily_etf_analysis/domain/etf.py`（ETF 实体 + signal 枚举）
3. `src/daily_etf_analysis/services/analysis_service.py`
4. `src/daily_etf_analysis/pipelines/daily_pipeline.py`
5. `src/daily_etf_analysis/api/v1/`（FastAPI 最小路由）
6. `tests/` 对应单元测试（fetcher mock + signal 规则）

---

该方案优先保证「可跑通 + 可扩展 + 可观测」，并与参考项目保持相同工程思想，但收敛到 ETF 场景，避免过度复杂化。
