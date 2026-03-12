from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from json_repair import repair_json
from pydantic import ValidationError

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisContext,
    EtfAnalysisResult,
    Trend,
)
from daily_etf_analysis.llm.report_schema import AnalysisReportSchema
from daily_etf_analysis.observability.metrics import inc_llm_call

logger = logging.getLogger(__name__)


class EtfAnalyzer:
    SYSTEM_PROMPT = """你是一位专注于趋势交易的 ETF 投资分析师，负责生成专业的【决策仪表盘】分析报告。

## 核心交易理念（必须严格遵守）

### 1. 严进策略（不追高）
- **绝对不追高**：当 ETF 价格偏离 MA5 超过 5% 时，坚决不买入
- **乖离率公式**：(现价 - MA5) / MA5 × 100%
- 乖离率 < 2%：最佳买点区间
- 乖离率 2-5%：可小仓介入
- 乖离率 > 5%：严禁追高！直接判定为"观望"

### 2. 趋势交易（顺势而为）
- **多头排列必须条件**：MA5 > MA10 > MA20
- 只做多头排列的 ETF，空头排列坚决不碰
- 均线发散上行优于均线粘合
- 趋势强度判断：看均线间距是否在扩大

### 3. 效率优先（筹码结构）
- 关注筹码集中度：90%集中度 < 15% 表示筹码集中
- 获利比例分析：70-90% 获利盘时需警惕获利回吐
- 平均成本与现价关系：现价高于平均成本 5-15% 为健康

### 4. 买点偏好（回踩支撑）
- **最佳买点**：缩量回踩 MA5 获得支撑
- **次优买点**：回踩 MA10 获得支撑
- **观望情况**：跌破 MA20 时观望

### 5. 风险排查重点
- 大额减持/赎回
- 基准指数大幅波动
- 资金面收缩/流动性下降
- 政策或行业利空

### 6. 强势趋势 ETF 放宽
- 强势趋势 ETF（多头排列且趋势强度高、量能配合）可适当放宽乖离率要求
- 仍需设置止损，不盲目追高

## 输出格式：决策仪表盘 JSON

请严格按照以下 JSON 格式输出，这是一个完整的【决策仪表盘】：

```json
{
    "stock_name": "ETF中文名称",
    "sentiment_score": 0-100整数,
    "trend_prediction": "强烈看多/看多/震荡/看空/强烈看空",
    "operation_advice": "买入/加仓/持有/减仓/卖出/观望",
    "decision_type": "buy/hold/sell",
    "confidence_level": "高/中/低",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句话核心结论（30字以内，直接告诉用户做什么）",
            "signal_type": "🟢买入信号/🟡持有观望/🔴卖出信号/⚠️风险警告",
            "time_sensitivity": "立即行动/今日内/本周内/不急",
            "position_advice": {
                "no_position": "空仓者建议：具体操作指引",
                "has_position": "持仓者建议：具体操作指引"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均线排列状态描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 当前价格数值,
                "ma5": MA5数值,
                "ma10": MA10数值,
                "ma20": MA20数值,
                "bias_ma5": 乖离率百分比数值,
                "bias_status": "安全/警戒/危险",
                "support_level": 支撑位价格,
                "resistance_level": 压力位价格
            },
            "volume_analysis": {
                "volume_ratio": 量比数值,
                "volume_status": "放量/缩量/平量",
                "turnover_rate": 换手率数值,
                "volume_meaning": "量能解读"
            },
            "chip_structure": {
                "profit_ratio": 获利盘比例,
                "avg_cost": 平均成本,
                "concentration": 筹码集中度,
                "chip_health": "健康/警惕/一般"
            }
        },

        "intelligence": {
            "latest_news": "最新重要信息摘要",
            "risk_alerts": ["风险1", "风险2"],
            "positive_catalysts": ["利好1", "利好2"],
            "earnings_outlook": "业绩预期",
            "sentiment_summary": "市场情绪总结"
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": 理想买入价,
                "secondary_buy": 次优买入价,
                "stop_loss": 止损位,
                "take_profit": 目标位
            },
            "position_strategy": {
                "suggested_position": "建议仓位",
                "entry_plan": "建仓策略",
                "risk_control": "风控策略"
            },
            "action_checklist": ["检查项1", "检查项2"]
        }
    },

    "analysis_summary": "完整分析总结（建议 150-300 字）",
    "key_points": "核心要点（可用逗号或分号分隔）",
    "risk_warning": "风险提示",
    "buy_reason": "买入理由（若适用）"
}
```

规则：
- 基于提供的因子与新闻。
- 数据质量低则降低信心并在风险中说明。
- 严格输出 JSON，不要附加 Markdown 包裹。
"""

    _SENSITIVE_TEXT = re.compile(
        r"(?i)(https?://\\S+|sk-[a-z0-9_\\-]+|token[=:]\\S+|api[_-]?key[=:]\\S+)"
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_available(self) -> bool:
        return bool(self.settings.openai_api_keys and self.settings.openai_model)

    def _resolve_endpoint(self) -> str:
        base_url = (self.settings.openai_base_url or "").strip()
        if not base_url:
            return "https://api.openai.com/v1/chat/completions"
        base = base_url.rstrip("/")
        if base.endswith("/v1/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _call_llm(self, prompt: str) -> tuple[str, str]:
        if not self.is_available():
            raise RuntimeError("No LLM model configured")

        model = self.settings.openai_model.strip() or "gpt-4o-mini"
        if model.startswith("openai/"):
            model = model.split("/", 1)[1]
        api_key = self.settings.openai_api_keys[0]
        endpoint = self._resolve_endpoint()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices")
            if not choices:
                raise ValueError("LLM response does not contain choices")
            first_choice = choices[0]
            message = (
                first_choice.get("message") if isinstance(first_choice, dict) else None
            )
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty LLM response")
            inc_llm_call("success", model)
            return content, model
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed with model %s: %s", model, exc)
            inc_llm_call("failed", model)
            raise RuntimeError(f"LLM call failed. Last error: {exc}") from exc

    def _build_prompt(self, context: EtfAnalysisContext) -> str:
        news_text = "\n".join(
            f"- {item.get('title', '')}: {item.get('snippet', '')}"
            for item in context.news_items[:5]
        )
        return (
            f"Symbol: {context.symbol}\n"
            f"Market: {context.market.value}\n"
            f"Code: {context.code}\n"
            f"Benchmark Index: {context.benchmark_index}\n"
            f"Factors JSON:\n{json.dumps(context.factors, ensure_ascii=False)}\n"
            f"News:\n{news_text or '- no recent news'}\n"
            "Provide ETF decision JSON."
        )

    def _parse_response(
        self, text: str, symbol: str, model_used: str
    ) -> EtfAnalysisResult:
        try:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            repaired = repair_json(cleaned)
            if isinstance(repaired, tuple):
                repaired_payload: Any = repaired[0]
            else:
                repaired_payload = repaired
            if isinstance(repaired_payload, dict | list):
                payload = repaired_payload
            elif isinstance(repaired_payload, str):
                payload = json.loads(repaired_payload)
            else:
                raise ValueError("Repaired JSON payload has unsupported type")
            if not isinstance(payload, dict):
                raise ValueError("LLM payload is not an object")

            parsed = AnalysisReportSchema.model_validate(payload)
            payload_dict = parsed.model_dump()
            missing_fields = _check_content_integrity(payload_dict)
            if missing_fields:
                _apply_placeholder_fill(payload_dict, missing_fields)

            score = _to_int(payload_dict.get("sentiment_score"), default=50)
            decision_type = _coerce_decision_type(
                payload_dict.get("decision_type"),
                payload_dict.get("operation_advice"),
                score,
            )
            action = _coerce_action(decision_type)
            confidence_level = payload_dict.get("confidence_level") or "中"
            confidence = _coerce_confidence(confidence_level)

            trend_prediction = str(payload_dict.get("trend_prediction") or "").strip()
            trend = _derive_trend(trend_prediction, score)

            dashboard = payload_dict.get("dashboard") or {}
            intelligence = dashboard.get("intelligence") or {}
            raw_risks = intelligence.get("risk_alerts") or []
            risk_alerts = _normalize_list(raw_risks)
            risk_warning = _sanitize_output_text(payload_dict.get("risk_warning"))
            if risk_warning:
                risk_alerts.append(risk_warning)

            analysis_summary = _sanitize_output_text(
                payload_dict.get("analysis_summary")
            )
            operation_advice = _sanitize_output_text(
                payload_dict.get("operation_advice")
            )
            if not operation_advice:
                operation_advice = _operation_from_action(action)

            summary = analysis_summary or operation_advice
            key_points = _split_key_points(payload_dict.get("key_points"))
            rationale = _sanitize_output_text(
                payload_dict.get("trend_analysis")
                or payload_dict.get("analysis_summary")
                or summary
            )

            degraded = False
            fallback_reason: str | None = None
            if confidence == Confidence.LOW and action != Action.HOLD:
                action = Action.HOLD
                decision_type = "hold"
                degraded = True
                fallback_reason = "LOW_CONFIDENCE_FORCED_HOLD"
                risk_alerts = list(risk_alerts) + [
                    "Low confidence; action downgraded to hold."
                ]

            return EtfAnalysisResult(
                symbol=symbol,
                name=str(payload_dict.get("stock_name") or symbol),
                score=score,
                trend=trend,
                action=action,
                confidence=confidence,
                summary=summary,
                key_points=key_points,
                risk_alerts=[
                    _sanitize_output_text(item, max_len=120)
                    for item in risk_alerts
                    if _sanitize_output_text(item, max_len=120)
                ],
                model_used=model_used,
                success=True,
                raw_response=text,
                horizon="next_trading_day",
                rationale=rationale,
                degraded=degraded,
                fallback_reason=fallback_reason,
                operation_advice=operation_advice,
                analysis_summary=analysis_summary or summary,
                trend_prediction=trend_prediction,
                decision_type=decision_type,
                confidence_level=str(confidence_level),
                dashboard=dashboard,
                llm_payload=payload_dict,
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return EtfAnalysisResult.neutral_fallback(symbol, str(exc))

    def analyze(self, context: EtfAnalysisContext) -> EtfAnalysisResult:
        prompt = self._build_prompt(context)
        content, model_used = self._call_llm(prompt)
        return self._parse_response(content, context.symbol, model_used)


def _sanitize_output_text(value: object, max_len: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    masked = EtfAnalyzer._SENSITIVE_TEXT.sub("***", text)
    return masked[:max_len]


def _split_key_points(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\n", ";")
    parts = [p.strip() for p in re.split(r"[;；,，]", text) if p.strip()]
    return parts[:6]


def _normalize_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _coerce_decision_type(
    decision_type: object, operation_advice: object, score: int
) -> str:
    if isinstance(decision_type, str) and decision_type.strip():
        normalized = decision_type.strip().lower()
        if normalized in {"buy", "hold", "sell"}:
            return normalized
    advice = str(operation_advice or "").strip()
    if advice:
        if any(token in advice for token in ["强烈买入", "买入", "加仓"]):
            return "buy"
        if any(token in advice for token in ["强烈卖出", "卖出", "减仓"]):
            return "sell"
    if score >= 65:
        return "buy"
    if score <= 35:
        return "sell"
    return "hold"


def _coerce_action(decision_type: str) -> Action:
    try:
        return Action(decision_type)
    except Exception:
        return Action.HOLD


def _coerce_confidence(level: object) -> Confidence:
    text = str(level or "").strip().lower()
    if text in {"high", "高"}:
        return Confidence.HIGH
    if text in {"medium", "中"}:
        return Confidence.MEDIUM
    if text in {"low", "低"}:
        return Confidence.LOW
    return Confidence.MEDIUM


def _derive_trend(prediction: str, score: int) -> Trend:
    if any(token in prediction for token in ["强烈看多", "看多"]):
        return Trend.BULLISH
    if any(token in prediction for token in ["强烈看空", "看空"]):
        return Trend.BEARISH
    if score >= 65:
        return Trend.BULLISH
    if score <= 35:
        return Trend.BEARISH
    return Trend.NEUTRAL


def _operation_from_action(action: Action) -> str:
    mapping = {
        Action.BUY: "买入",
        Action.HOLD: "观望",
        Action.SELL: "卖出",
    }
    return mapping.get(action, "观望")


def _to_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _check_content_integrity(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if payload.get("sentiment_score") is None:
        missing.append("sentiment_score")
    if not (payload.get("operation_advice") or "").strip():
        missing.append("operation_advice")
    if not (payload.get("analysis_summary") or "").strip():
        missing.append("analysis_summary")

    dashboard = payload.get("dashboard") or {}
    core = dashboard.get("core_conclusion") or {}
    if not (core.get("one_sentence") or "").strip():
        missing.append("dashboard.core_conclusion.one_sentence")
    intel = dashboard.get("intelligence") or {}
    if "risk_alerts" not in intel:
        missing.append("dashboard.intelligence.risk_alerts")

    decision_type = payload.get("decision_type") or ""
    if decision_type in ("buy", "hold"):
        battle = dashboard.get("battle_plan") or {}
        sniper = battle.get("sniper_points") or {}
        if not (sniper.get("stop_loss") or ""):
            missing.append("dashboard.battle_plan.sniper_points.stop_loss")
    return missing


def _apply_placeholder_fill(payload: dict[str, Any], missing_fields: list[str]) -> None:
    for field in missing_fields:
        if field == "sentiment_score":
            payload["sentiment_score"] = 50
        elif field == "operation_advice":
            payload["operation_advice"] = payload.get("operation_advice") or "待补充"
        elif field == "analysis_summary":
            payload["analysis_summary"] = payload.get("analysis_summary") or "待补充"
        elif field == "dashboard.core_conclusion.one_sentence":
            dashboard = payload.setdefault("dashboard", {})
            core = dashboard.setdefault("core_conclusion", {})
            core["one_sentence"] = core.get("one_sentence") or "待补充"
        elif field == "dashboard.intelligence.risk_alerts":
            dashboard = payload.setdefault("dashboard", {})
            intel = dashboard.setdefault("intelligence", {})
            if "risk_alerts" not in intel:
                intel["risk_alerts"] = []
        elif field == "dashboard.battle_plan.sniper_points.stop_loss":
            dashboard = payload.setdefault("dashboard", {})
            battle = dashboard.get("battle_plan")
            if not isinstance(battle, dict):
                battle = {}
                dashboard["battle_plan"] = battle
            sniper = battle.setdefault("sniper_points", {})
            sniper["stop_loss"] = sniper.get("stop_loss") or "待补充"
