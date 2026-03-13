from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from typing import Any

import httpx

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.observability.metrics import inc_llm_call

logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """你是一位ETF策略师，需要基于提供的数据生成“全局短评”。

要求：
1) 中文输出，1-3段自然短评。
2) 最后一行必须以“**一句话结论**：”开头，结论不超过30字。
3) 只使用提供的数据，不要编造。
4) 避免列表或Markdown标题，保持简洁段落。
"""


def build_global_summary_text(
    *,
    report_rows: list[dict[str, Any]],
    report_date: date,
    settings: Settings | None = None,
) -> str:
    payload = build_global_summary_payload(
        report_rows=report_rows, report_date=report_date
    )
    if payload["total"] == 0:
        return "今日无可用ETF分析结果。\n**一句话结论**：等待更多数据。"

    cfg = settings or get_settings()
    if not _llm_available(cfg):
        return _fallback_summary(payload)

    try:
        content = _call_llm(cfg, payload)
        if content:
            return content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Global summary LLM failed: %s", exc)
    return _fallback_summary(payload)


def build_global_summary_payload(
    *, report_rows: list[dict[str, Any]], report_date: date
) -> dict[str, Any]:
    total = len(report_rows)
    scores: list[float] = []
    for row in report_rows:
        score = row.get("score")
        if isinstance(score, int | float):
            scores.append(float(score))
    avg_score = round(sum(scores) / len(scores), 2) if scores else None

    action_counts = Counter(
        str(row.get("action") or "hold").lower() for row in report_rows
    )
    trend_counts = Counter(
        str(row.get("trend") or "neutral").lower() for row in report_rows
    )

    top_rows = sorted(
        report_rows, key=lambda item: float(item.get("score") or 0), reverse=True
    )[:3]
    top_symbols = [
        {
            "symbol": row.get("symbol"),
            "score": row.get("score"),
            "action": row.get("action"),
            "trend": row.get("trend"),
        }
        for row in top_rows
    ]

    risk_counter: Counter[str] = Counter()
    theme_positive: list[str] = []
    theme_negative: list[str] = []
    theme_sentiments: list[str] = []
    for row in report_rows:
        alerts = row.get("risk_alerts") or []
        if isinstance(alerts, list):
            for alert in alerts:
                text = str(alert).strip()
                if text:
                    risk_counter[text] += 1
        snapshot = row.get("context_snapshot") or {}
        if isinstance(snapshot, dict):
            theme_intel = snapshot.get("theme_intel") or {}
            if isinstance(theme_intel, dict):
                positives = theme_intel.get("positive_catalysts") or []
                negatives = theme_intel.get("risk_alerts") or []
                sentiment = str(theme_intel.get("sentiment_summary") or "").strip()
                if isinstance(positives, list):
                    theme_positive.extend([str(x) for x in positives if str(x).strip()])
                if isinstance(negatives, list):
                    theme_negative.extend([str(x) for x in negatives if str(x).strip()])
                if sentiment:
                    theme_sentiments.append(sentiment)

    risk_top = [{"text": k, "count": v} for k, v in risk_counter.most_common(5)]
    theme_payload = {
        "positive": theme_positive[:5],
        "negative": theme_negative[:5],
        "sentiments": theme_sentiments[:5],
    }

    return {
        "date": report_date.isoformat(),
        "total": total,
        "avg_score": avg_score,
        "action_counts": dict(action_counts),
        "trend_counts": dict(trend_counts),
        "top_symbols": top_symbols,
        "risk_top": risk_top,
        "theme_summary": theme_payload,
    }


def _fallback_summary(payload: dict[str, Any]) -> str:
    total = payload.get("total", 0)
    avg_score = payload.get("avg_score")
    actions = payload.get("action_counts", {})
    buy = actions.get("buy", 0)
    hold = actions.get("hold", 0)
    sell = actions.get("sell", 0)
    trend = payload.get("trend_counts", {})
    main_trend = max(trend.items(), key=lambda item: item[1])[0] if trend else "neutral"
    trend_map = {
        "bullish": "看多",
        "bearish": "看空",
        "neutral": "震荡",
        "non_bullish": "震荡",
    }
    main_trend_text = trend_map.get(str(main_trend).lower(), "震荡")
    risk_top = payload.get("risk_top", [])
    risk_text = risk_top[0]["text"] if risk_top else "暂无明显集中风险"
    line1 = f"今日共分析{total}只ETF，买入{buy}、观望{hold}、卖出{sell}，平均评分{avg_score}。"
    line2 = f"整体趋势以{main_trend_text}为主，主要风险关注：{risk_text}。"
    line3 = "**一句话结论**：当前以观望为主，等待趋势确认。"
    return "\n".join([line1, line2, line3])


def _llm_available(settings: Settings) -> bool:
    return bool(settings.openai_api_keys and settings.openai_model)


def _resolve_endpoint(settings: Settings) -> str:
    base_url = (settings.openai_base_url or "").strip()
    if not base_url:
        return "https://api.openai.com/v1/chat/completions"
    base = base_url.rstrip("/")
    if base.endswith("/v1/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _call_llm(settings: Settings, payload: dict[str, Any]) -> str:
    model = settings.openai_model.strip() or "gpt-4o-mini"
    if model.startswith("openai/"):
        model = model.split("/", 1)[1]
    api_key = settings.openai_api_keys[0]
    endpoint = _resolve_endpoint(settings)
    prompt = (
        "请根据以下汇总数据生成ETF全局短评：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = httpx.post(
            endpoint,
            headers=headers,
            json=body,
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Global summary LLM response missing choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Global summary LLM response empty")
        inc_llm_call("success", model)
        return content.strip()
    except Exception as exc:  # noqa: BLE001
        inc_llm_call("failed", model)
        raise RuntimeError(f"Global summary LLM failed: {exc}") from exc
