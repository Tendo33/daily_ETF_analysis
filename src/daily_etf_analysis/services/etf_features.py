from __future__ import annotations

from dataclasses import dataclass
from math import log10, sqrt
from typing import Any

from daily_etf_analysis.domain import EtfDailyBar, EtfRealtimeQuote


@dataclass(frozen=True, slots=True)
class EtfFeatureResult:
    payload: dict[str, Any]


def compute_etf_features(
    *,
    bars: list[EtfDailyBar],
    quote: EtfRealtimeQuote | None,
    benchmark_bars: list[EtfDailyBar] | None = None,
    theme_tags: list[str] | None = None,
) -> dict[str, Any]:
    if not bars:
        return {
            "data_quality": "empty",
            "theme_tags": theme_tags or [],
        }

    latest_bar = bars[-1]
    latest_close = latest_bar.close
    latest_price = quote.price if quote is not None else latest_close

    avg_amount_20 = _avg_amount(bars[-20:])
    liquidity_score = _liquidity_score(avg_amount_20)
    spread_proxy = _spread_proxy(latest_bar)
    intraday_gap = _pct_change(latest_close, latest_price)

    tracking_error = _tracking_error(bars, benchmark_bars, window=20)

    missing: list[str] = []
    premium_discount_pct: float | None = None
    if premium_discount_pct is None:
        missing.append("premium_discount")
    if tracking_error is None:
        missing.append("tracking_error")

    data_quality = "ok" if not missing else "limited"

    return {
        "premium_discount_pct": premium_discount_pct,
        "tracking_error": tracking_error,
        "tracking_window": 20,
        "share_change_pct": None,
        "aum_change_pct": None,
        "liquidity_score": liquidity_score,
        "avg_amount_20": avg_amount_20,
        "spread_proxy": spread_proxy,
        "intraday_gap_pct": intraday_gap,
        "theme_tags": theme_tags or [],
        "data_quality": data_quality,
        "missing_fields": missing,
    }


def _avg_amount(bars: list[EtfDailyBar]) -> float | None:
    if not bars:
        return None
    values: list[float] = []
    for bar in bars:
        amount = bar.amount
        if amount is None and bar.volume is not None:
            amount = bar.volume * bar.close
        if amount is not None and amount > 0:
            values.append(float(amount))
    if not values:
        return None
    return sum(values) / len(values)


def _liquidity_score(avg_amount: float | None) -> int | None:
    if avg_amount is None or avg_amount <= 0:
        return None
    log_val = log10(max(avg_amount, 1.0))
    score = int((log_val - 6) * 20)
    return max(0, min(100, score))


def _spread_proxy(bar: EtfDailyBar) -> float | None:
    if bar.close <= 0:
        return None
    spread = (bar.high - bar.low) / bar.close * 100
    return round(spread, 4)


def _tracking_error(
    bars: list[EtfDailyBar],
    benchmark_bars: list[EtfDailyBar] | None,
    window: int = 20,
) -> float | None:
    if not benchmark_bars:
        return None
    aligned = _align_returns(bars, benchmark_bars, window=window)
    if len(aligned) < 3:
        return None
    diff = [(a - b) for a, b in aligned]
    mean = sum(diff) / len(diff)
    var = sum((x - mean) ** 2 for x in diff) / (len(diff) - 1)
    return round((var**0.5) * sqrt(252), 4)


def _align_returns(
    bars: list[EtfDailyBar],
    benchmark_bars: list[EtfDailyBar],
    window: int,
) -> list[tuple[float, float]]:
    etf_by_date = {bar.trade_date: bar.close for bar in bars}
    bench_by_date = {bar.trade_date: bar.close for bar in benchmark_bars}
    common_dates = sorted(set(etf_by_date) & set(bench_by_date))
    if len(common_dates) < 3:
        return []
    common_dates = common_dates[-(window + 1) :]
    aligned: list[tuple[float, float]] = []
    for idx in range(1, len(common_dates)):
        d0 = common_dates[idx - 1]
        d1 = common_dates[idx]
        etf_prev = etf_by_date.get(d0)
        etf_cur = etf_by_date.get(d1)
        bench_prev = bench_by_date.get(d0)
        bench_cur = bench_by_date.get(d1)
        if (
            etf_prev is None
            or etf_cur is None
            or bench_prev is None
            or bench_cur is None
        ):
            continue
        etf_ret = (etf_cur - etf_prev) / etf_prev if etf_prev else 0.0
        bench_ret = (bench_cur - bench_prev) / bench_prev if bench_prev else 0.0
        aligned.append((etf_ret, bench_ret))
    return aligned


def _pct_change(start: float, end: float) -> float | None:
    if start == 0:
        return None
    return round((end - start) / start * 100, 4)
