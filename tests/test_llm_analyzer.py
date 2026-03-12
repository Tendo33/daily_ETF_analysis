from __future__ import annotations

from datetime import date

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.core.time import utc_now_naive
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
            symbol=symbol, price=101, quote_time=utc_now_naive(), source="mock"
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
    settings = Settings(openai_model="gpt-4o-mini", openai_api_keys=["sk-test"])
    analyzer = EtfAnalyzer(settings=settings)
    result = analyzer._parse_response("not-json", "US:QQQ", "openai/gpt-4o-mini")  # noqa: SLF001
    assert result.success is False
    assert result.score == 50


def test_llm_call_uses_base_url_and_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        openai_model="gpt-4o-mini",
        openai_api_keys=["sk-test-123456"],
        openai_base_url="https://api.example.com/v1",
    )
    analyzer = EtfAnalyzer(settings=settings)
    calls: list[dict[str, object]] = []

    class _Resp:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _Resp(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"score":72,"trend":"bullish","action":"buy","confidence":"medium","risk_alerts":["x"],"summary":"ok","key_points":["a"]}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("httpx.post", fake_post)
    result = analyzer.analyze(_context())

    assert calls
    assert calls[0]["url"] == "https://api.example.com/v1/chat/completions"
    assert result.success is True
    assert result.model_used == "gpt-4o-mini"


def test_low_confidence_action_is_downgraded_to_hold() -> None:
    settings = Settings(openai_model="gpt-4o-mini", openai_api_keys=["sk-test"])
    analyzer = EtfAnalyzer(settings=settings)
    raw = (
        '{"score":65,"trend":"bullish","action":"buy","confidence":"low",'
        '"risk_alerts":["volatility"],"summary":"cautious","key_points":["a"],'
        '"horizon":"next_trading_day","rationale":"weak conviction"}'
    )
    result = analyzer._parse_response(raw, "US:QQQ", "openai/gpt-4o-mini")  # noqa: SLF001
    assert result.success is True
    assert result.action.value == "hold"
    assert result.degraded is True
    assert result.fallback_reason == "LOW_CONFIDENCE_FORCED_HOLD"
