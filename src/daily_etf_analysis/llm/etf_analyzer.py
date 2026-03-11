from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from json_repair import repair_json
from pydantic import BaseModel, Field, ValidationError

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisContext,
    EtfAnalysisResult,
    Trend,
)
from daily_etf_analysis.observability.metrics import inc_llm_call

logger = logging.getLogger(__name__)


class _LlmResultModel(BaseModel):
    score: int = Field(ge=0, le=100)
    trend: str
    action: str
    confidence: str
    risk_alerts: list[str] = Field(default_factory=list)
    summary: str
    key_points: list[str] = Field(default_factory=list)
    horizon: str = "next_trading_day"
    rationale: str = ""


class EtfAnalyzer:
    SYSTEM_PROMPT = """You are an ETF decision engine.
Output JSON only:
{
  "score": 0-100,
  "trend": "bullish|neutral|bearish",
  "action": "buy|hold|sell",
  "confidence": "low|medium|high",
  "horizon": "next_trading_day",
  "risk_alerts": ["..."],
  "rationale": "why this action for next session",
  "summary": "short summary",
  "key_points": ["...", "..."]
}
Rules:
- Base your decision on provided factors and news only.
- If data quality is low, lower confidence and mention uncertainty.
- Never output markdown wrappers.
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
            parsed: _LlmResultModel = _LlmResultModel.model_validate(payload)
            risk_alerts = [
                self._sanitize_output_text(item, max_len=120)
                for item in parsed.risk_alerts
                if self._sanitize_output_text(item, max_len=120)
            ]
            summary = self._sanitize_output_text(parsed.summary, max_len=240)
            rationale = self._sanitize_output_text(
                parsed.rationale or parsed.summary,
                max_len=500,
            )
            key_points = [
                self._sanitize_output_text(item, max_len=140)
                for item in parsed.key_points
                if self._sanitize_output_text(item, max_len=140)
            ]
            action = Action(parsed.action)
            confidence = Confidence(parsed.confidence)
            degraded = False
            fallback_reason: str | None = None
            if confidence == Confidence.LOW and action != Action.HOLD:
                action = Action.HOLD
                degraded = True
                fallback_reason = "LOW_CONFIDENCE_FORCED_HOLD"
                risk_alerts = list(risk_alerts) + [
                    "Low confidence; action downgraded to hold."
                ]
            return EtfAnalysisResult(
                symbol=symbol,
                score=parsed.score,
                trend=Trend(parsed.trend),
                action=action,
                confidence=confidence,
                summary=summary,
                key_points=key_points,
                risk_alerts=risk_alerts,
                model_used=model_used,
                success=True,
                raw_response=text,
                horizon=parsed.horizon or "next_trading_day",
                rationale=rationale,
                degraded=degraded,
                fallback_reason=fallback_reason,
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return EtfAnalysisResult.neutral_fallback(
                symbol=symbol, error_message=f"LLM output parse failed: {exc}"
            )

    def analyze(self, context: EtfAnalysisContext) -> EtfAnalysisResult:
        if not self.is_available():
            return EtfAnalysisResult.neutral_fallback(
                symbol=context.symbol, error_message="LLM not configured"
            )
        try:
            prompt = self._build_prompt(context)
            raw, model_used = self._call_llm(prompt)
            result = self._parse_response(raw, context.symbol, model_used)
            if not result.raw_response:
                result.raw_response = raw
            return result
        except Exception as exc:  # noqa: BLE001
            return EtfAnalysisResult.neutral_fallback(
                symbol=context.symbol, error_message=str(exc)
            )

    def _sanitize_output_text(self, text: object, *, max_len: int) -> str:
        value = str(text).strip()
        if not value:
            return ""
        value = self._SENSITIVE_TEXT.sub("***", value)
        return value[:max_len]
