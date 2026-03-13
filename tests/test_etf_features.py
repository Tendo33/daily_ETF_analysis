from __future__ import annotations

from datetime import date, timedelta

from daily_etf_analysis.domain import EtfDailyBar
from daily_etf_analysis.services.etf_features import compute_etf_features


def _make_bars(symbol: str, start: date, count: int, base: float) -> list[EtfDailyBar]:
    bars: list[EtfDailyBar] = []
    for idx in range(count):
        d = start + timedelta(days=idx)
        price = base + idx * 0.1
        bars.append(
            EtfDailyBar(
                symbol=symbol,
                trade_date=d,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1_000_000 + idx * 1000,
                amount=price * (1_000_000 + idx * 1000),
                pct_chg=None,
                source="test",
            )
        )
    return bars


def test_compute_etf_features_without_benchmark() -> None:
    bars = _make_bars("CN:159392", date(2026, 1, 1), 30, 1.0)
    features = compute_etf_features(bars=bars, quote=None, benchmark_bars=None)
    assert features["data_quality"] == "limited"
    assert features["liquidity_score"] is not None
    assert features["spread_proxy"] is not None


def test_compute_etf_features_with_benchmark() -> None:
    bars = _make_bars("CN:159392", date(2026, 1, 1), 30, 1.0)
    benchmark = _make_bars("CN:159659", date(2026, 1, 1), 30, 1.2)
    features = compute_etf_features(
        bars=bars, quote=None, benchmark_bars=benchmark, theme_tags=["航空航天"]
    )
    assert features["tracking_error"] is not None
    assert features["theme_tags"] == ["航空航天"]
