from __future__ import annotations

from daily_etf_analysis.services.market_review import build_market_review


def test_build_market_review_basic() -> None:
    rows = [
        {
            "symbol": "CN:159659",
            "score": 80,
            "trend": "bullish",
            "action": "buy",
            "risk_alerts": ["risk1"],
        },
        {
            "symbol": "CN:159920",
            "score": 40,
            "trend": "bearish",
            "action": "sell",
            "risk_alerts": [],
        },
    ]
    industry_map = {"Tech": ["CN:159659"]}
    review = build_market_review(rows, industry_map=industry_map)
    assert review["total"] == 2
    assert review["avg_score"] == 60.0
    assert review["trend_counts"]["bullish"] == 1
    assert review["action_counts"]["sell"] == 1
    assert review["top"][0]["symbol"] == "CN:159659"
    assert review["bottom"][0]["symbol"] == "CN:159920"
    assert review["risk_alerts"][0]["symbol"] == "CN:159659"
    assert review["industry"][0]["industry"] == "Tech"


def test_build_market_review_handles_missing_scores() -> None:
    rows = [
        {
            "symbol": "CN:159659",
            "score": None,
            "trend": "bullish",
            "action": "buy",
            "risk_alerts": [],
        },
        {
            "symbol": "CN:159920",
            "score": "not-a-number",
            "trend": "bearish",
            "action": "sell",
            "risk_alerts": [],
        },
        {
            "symbol": "CN:159915",
            "score": 70,
            "trend": "neutral",
            "action": "hold",
            "risk_alerts": [],
        },
    ]

    review = build_market_review(rows)

    assert review["top"][0]["symbol"] == "CN:159915"


def test_build_market_review_industry_taskx_fields() -> None:
    rows = [
        {
            "symbol": "CN:159659",
            "score": 82,
            "trend": "bullish",
            "action": "buy",
            "risk_alerts": ["valuation_high", "liquidity_low"],
        },
        {
            "symbol": "CN:159915",
            "score": 55,
            "trend": "neutral",
            "action": "hold",
            "risk_alerts": ["liquidity_low"],
        },
    ]
    review = build_market_review(
        rows,
        industry_map={"Tech": ["CN:159659", "CN:159915"]},
        history_by_symbol={
            "CN:159659": [
                {"action": "buy", "trend": "bullish", "trade_date": "2026-03-10"},
                {"action": "hold", "trend": "neutral", "trade_date": "2026-03-09"},
            ],
            "CN:159915": [
                {"action": "hold", "trend": "neutral", "trade_date": "2026-03-10"},
                {"action": "hold", "trend": "neutral", "trade_date": "2026-03-09"},
            ],
        },
        trend_window_days=5,
        risk_top_n=1,
        recommend_weights={"buy": 1, "hold": 0, "sell": -1, "score_weight": 0.5},
    )

    industry = review["industry"][0]
    assert industry["industry"] == "Tech"
    assert industry["trend_change_count"] == 1
    assert industry["risk_top"][0]["alert"] == "liquidity_low"
    assert industry["recommend_level"] in {"overweight", "neutral", "underweight"}
