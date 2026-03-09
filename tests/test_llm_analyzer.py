from __future__ import annotations

from datetime import date, datetime

import litellm

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import (
    EtfAnalysisContext,
    EtfDailyBar,
    EtfRealtimeQuote,
    Market,
)
from daily_etf_analysis.llm import EtfAnalyzer


def _context(symbol: str = "US:QQQ") -> EtfAnalysisContext:
    return EtfAnalysisContext(
        symbol=symbol,
        market=Market.US,
        code="QQQ",
        benchmark_index="NDX",
        factors={"ma5": 100, "ma10": 99, "ma20": 98},
        latest_quote=EtfRealtimeQuote(
            symbol=symbol, price=101, quote_time=datetime.utcnow(), source="mock"
        ),
        latest_bar=EtfDailyBar(
            symbol=symbol,
            trade_date=date.today(),
            open=99,
            high=101,
            low=98,
            close=100,
            source="mock",
        ),
        news_items=[{"title": "news", "snippet": "snip"}],
    )


def test_parse_failure_returns_neutral_fallback() -> None:
    settings = Settings(litellm_model="openai/gpt-4o-mini", llm_model_list=[])
    analyzer = EtfAnalyzer(settings=settings)
    result = analyzer._parse_response("not-json", "US:QQQ", "openai/gpt-4o-mini")  # noqa: SLF001
    assert result.success is False
    assert result.score == 50


def test_llm_fallback_model_used(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        litellm_model="openai/primary-model",
        litellm_fallback_models=["openai/fallback-model"],
        openai_api_keys=["sk-test-123456"],
        llm_model_list=[],
    )
    analyzer = EtfAnalyzer(settings=settings)
    analyzer.router = None
    calls: list[str] = []

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content: str) -> None:
            self.choices = [_Choice(content)]

    def fake_completion(**kwargs):  # type: ignore[no-untyped-def]
        model = kwargs["model"]
        calls.append(model)
        if model == "openai/primary-model":
            raise RuntimeError("primary failed")
        return _Resp(
            '{"score":72,"trend":"bullish","action":"buy","confidence":"medium","risk_alerts":["x"],"summary":"ok","key_points":["a"]}'
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    result = analyzer.analyze(_context())

    assert calls == ["openai/primary-model", "openai/fallback-model"]
    assert result.success is True
    assert result.model_used == "openai/fallback-model"
