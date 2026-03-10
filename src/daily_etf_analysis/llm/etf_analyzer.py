from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from json_repair import repair_json
from litellm import Router
from pydantic import BaseModel, Field, ValidationError

from daily_etf_analysis.config.settings import (
    Settings,
    extra_litellm_params,
    get_api_keys_for_model,
    get_settings,
)
from daily_etf_analysis.domain import (
    Action,
    Confidence,
    EtfAnalysisContext,
    EtfAnalysisResult,
    Trend,
)

logger = logging.getLogger(__name__)


class _LlmResultModel(BaseModel):
    score: int = Field(ge=0, le=100)
    trend: str
    action: str
    confidence: str
    risk_alerts: list[str] = Field(default_factory=list)
    summary: str
    key_points: list[str] = Field(default_factory=list)


class EtfAnalyzer:
    SYSTEM_PROMPT = """You are an ETF decision engine.
Output JSON only:
{
  "score": 0-100,
  "trend": "bullish|neutral|bearish",
  "action": "buy|hold|sell",
  "confidence": "low|medium|high",
  "risk_alerts": ["..."],
  "summary": "short summary",
  "key_points": ["...", "..."]
}
Rules:
- Base your decision on provided factors and news only.
- If data quality is low, lower confidence and mention uncertainty.
- Never output markdown wrappers.
"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.router: Router | None = None
        self._init_router()

    def _init_router(self) -> None:
        if not self.settings.llm_model_list:
            return
        self.router = Router(
            model_list=self.settings.llm_model_list,
            routing_strategy="simple-shuffle",
            num_retries=2,
        )

    def is_available(self) -> bool:
        return bool(self.settings.litellm_model or self.settings.llm_model_list)

    def _candidate_models(self) -> list[str]:
        models = [self.settings.litellm_model] + self.settings.litellm_fallback_models
        dedup = [m for m in models if m]
        if not dedup and self.settings.llm_model_list:
            dedup = list(
                dict.fromkeys(
                    item["litellm_params"]["model"]
                    for item in self.settings.llm_model_list
                )
            )
        return dedup

    def _call_llm(self, prompt: str) -> tuple[str, str]:
        last_error: Exception | None = None
        models = self._candidate_models()
        if not models:
            raise RuntimeError("No LLM model configured")

        for model in models:
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.settings.llm_temperature,
                    "max_tokens": self.settings.llm_max_tokens,
                    "timeout": self.settings.llm_timeout_seconds,
                }
                if self.router:
                    response = self.router.completion(**kwargs)
                else:
                    keys = get_api_keys_for_model(model, self.settings)
                    if keys:
                        kwargs["api_key"] = keys[0]
                    kwargs.update(extra_litellm_params(model, self.settings))
                    response = litellm.completion(**kwargs)
                choices = getattr(response, "choices", None)
                if not choices:
                    raise ValueError("LLM response does not contain choices")
                first_choice = choices[0]
                message = getattr(first_choice, "message", None)
                content = (
                    getattr(message, "content", None) if message is not None else None
                )
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Empty LLM response")
                return content, model
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM call failed with model %s: %s", model, exc)
                last_error = exc
                continue
        raise RuntimeError(f"All LLM models failed. Last error: {last_error}")

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
            return EtfAnalysisResult(
                symbol=symbol,
                score=parsed.score,
                trend=Trend(parsed.trend),
                action=Action(parsed.action),
                confidence=Confidence(parsed.confidence),
                summary=parsed.summary,
                key_points=parsed.key_points,
                risk_alerts=parsed.risk_alerts,
                model_used=model_used,
                success=True,
                raw_response=text,
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
