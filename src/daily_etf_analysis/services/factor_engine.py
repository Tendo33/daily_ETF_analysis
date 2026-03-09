from __future__ import annotations

from math import sqrt

from daily_etf_analysis.domain import EtfDailyBar, EtfRealtimeQuote


def compute_factors(
    bars: list[EtfDailyBar], quote: EtfRealtimeQuote | None = None
) -> dict[str, float | int | str | None]:
    if not bars:
        return {"data_quality": "empty"}

    closes = [bar.close for bar in bars]
    volumes = [bar.volume or 0.0 for bar in bars]
    latest_close = closes[-1]
    latest_price = quote.price if quote is not None else latest_close
    prev_close = closes[-2] if len(closes) > 1 else latest_close

    ma5 = _mean(closes[-5:])
    ma10 = _mean(closes[-10:])
    ma20 = _mean(closes[-20:])
    ma20_prev = _mean(closes[-25:-5]) if len(closes) >= 25 else ma20

    return_20 = _pct_change(closes[-20], latest_close) if len(closes) >= 20 else None
    return_60 = _pct_change(closes[-60], latest_close) if len(closes) >= 60 else None

    rets = []
    for idx in range(1, min(len(closes), 60)):
        prev = closes[idx - 1]
        if prev:
            rets.append((closes[idx] - prev) / prev)
    volatility = _std(rets[-20:]) * sqrt(252) if rets else None

    trailing = closes[-60:] if len(closes) >= 60 else closes
    max_drawdown = _max_drawdown(trailing)

    avg_vol20 = _mean(volumes[-20:]) if volumes else 0.0
    volume_ratio = (volumes[-1] / avg_vol20) if avg_vol20 else None

    factors: dict[str, float | int | str | None] = {
        "latest_price": latest_price,
        "latest_close": latest_close,
        "change_pct": _pct_change(prev_close, latest_price) if prev_close else None,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma20_slope": (ma20 - ma20_prev) / ma20_prev if ma20_prev else 0.0,
        "return_20": return_20,
        "return_60": return_60,
        "volatility_annualized": volatility,
        "max_drawdown_60": max_drawdown,
        "volume_ratio": volume_ratio,
        "trend_alignment": "bullish" if ma5 > ma10 > ma20 else "non_bullish",
        "data_points": len(bars),
        "data_quality": "ok" if len(bars) >= 30 else "limited",
    }
    if quote is not None:
        factors["turnover"] = quote.turnover
        factors["realtime_change_pct"] = quote.change_pct
    return factors


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end - start) / start


def _std(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = _mean(values)
    var = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return var**0.5


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for value in values:
        if value > peak:
            peak = value
        if peak:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
    return max_dd
