from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


class BacktestEngine:
    def __init__(self, eval_window_days: int = 20) -> None:
        if eval_window_days < 1:
            raise ValueError("eval_window_days must be >= 1")
        self.eval_window_days = eval_window_days

    def run(
        self,
        signals: list[dict[str, Any]],
        prices_by_symbol: dict[str, list[dict[str, Any]]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        grouped_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for signal in signals:
            symbol = str(signal.get("symbol", "")).upper()
            if not symbol:
                continue
            grouped_signals[symbol].append(signal)

        symbol_rows: list[dict[str, Any]] = []
        total_samples = 0
        total_evaluated = 0
        total_skipped = 0
        total_hits = 0
        total_returns: list[float] = []

        for symbol, items in grouped_signals.items():
            item_sorted = sorted(items, key=lambda x: x["trade_date"])
            price_rows = sorted(
                prices_by_symbol.get(symbol, []), key=lambda x: x["trade_date"]
            )
            perf = self._evaluate_symbol(symbol, item_sorted, price_rows)
            symbol_rows.append(perf)

            total_samples += int(perf["sample_count"])
            total_evaluated += int(perf["evaluated_count"])
            total_skipped += int(perf["skipped_count"])
            total_hits += int(perf["details"]["hit_count"])
            total_returns.extend(perf["details"]["signed_returns"])

        run_summary = self._build_metrics(
            total_samples=total_samples,
            evaluated_count=total_evaluated,
            skipped_count=total_skipped,
            hit_count=total_hits,
            signed_returns=total_returns,
        )
        return run_summary, symbol_rows

    def _evaluate_symbol(
        self,
        symbol: str,
        signals: list[dict[str, Any]],
        prices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        price_lookup = {
            p["trade_date"]: idx
            for idx, p in enumerate(prices)
            if isinstance(p.get("trade_date"), date)
        }

        signed_returns: list[float] = []
        hit_count = 0
        evaluated_count = 0
        skipped_count = 0

        for signal in signals:
            trade_date = signal.get("trade_date")
            action = str(signal.get("action", "hold")).lower()
            if not isinstance(trade_date, date):
                skipped_count += 1
                continue

            idx = price_lookup.get(trade_date)
            if idx is None:
                skipped_count += 1
                continue

            target_idx = idx + self.eval_window_days
            if target_idx >= len(prices):
                skipped_count += 1
                continue

            current_close = _to_float(prices[idx].get("close"))
            target_close = _to_float(prices[target_idx].get("close"))
            if current_close is None or target_close is None or current_close == 0:
                skipped_count += 1
                continue

            raw_return = (target_close - current_close) / current_close
            signed_return = raw_return * _action_direction(action)
            evaluated_count += 1
            signed_returns.append(signed_return)
            if _is_direction_hit(action, raw_return):
                hit_count += 1

        metrics = self._build_metrics(
            total_samples=len(signals),
            evaluated_count=evaluated_count,
            skipped_count=skipped_count,
            hit_count=hit_count,
            signed_returns=signed_returns,
        )
        metrics["symbol"] = symbol
        metrics["details"] = {
            "hit_count": hit_count,
            "signed_returns": signed_returns,
        }
        return metrics

    def _build_metrics(
        self,
        total_samples: int,
        evaluated_count: int,
        skipped_count: int,
        hit_count: int,
        signed_returns: list[float],
    ) -> dict[str, Any]:
        direction_hit_rate = None
        avg_return = None
        win_rate = None
        max_drawdown = None

        if evaluated_count > 0:
            direction_hit_rate = round(hit_count / evaluated_count, 6)
            avg_return = round(sum(signed_returns) / evaluated_count, 6)
            win_count = len([value for value in signed_returns if value > 0])
            win_rate = round(win_count / evaluated_count, 6)
            max_drawdown = round(_max_drawdown(signed_returns), 6)

        return {
            "sample_count": total_samples,
            "total_samples": total_samples,
            "evaluated_count": evaluated_count,
            "evaluated_samples": evaluated_count,
            "skipped_count": skipped_count,
            "direction_hit_rate": direction_hit_rate,
            "avg_return": avg_return,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
        }


def _action_direction(action: str) -> int:
    mapping = {"buy": 1, "hold": 0, "sell": -1}
    return mapping.get(action.lower(), 0)


def _is_direction_hit(action: str, raw_return: float) -> bool:
    normalized = action.lower()
    if normalized == "buy":
        return raw_return > 0
    if normalized == "sell":
        return raw_return < 0
    if normalized == "hold":
        return abs(raw_return) <= 0.01
    return False


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _max_drawdown(signed_returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for ret in signed_returns:
        equity *= 1.0 + ret
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        max_dd = min(max_dd, drawdown)
    return max_dd
