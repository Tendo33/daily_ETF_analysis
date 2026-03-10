from __future__ import annotations

from datetime import date

from daily_etf_analysis.backtest.engine import BacktestEngine


def test_backtest_engine_metrics_for_fixed_window() -> None:
    engine = BacktestEngine(eval_window_days=2)
    signals = [
        {"symbol": "US:QQQ", "trade_date": date(2026, 3, 1), "action": "buy"},
        {"symbol": "US:QQQ", "trade_date": date(2026, 3, 2), "action": "sell"},
    ]
    prices = {
        "US:QQQ": [
            {"trade_date": date(2026, 3, 1), "close": 100.0},
            {"trade_date": date(2026, 3, 2), "close": 110.0},
            {"trade_date": date(2026, 3, 3), "close": 120.0},
            {"trade_date": date(2026, 3, 4), "close": 130.0},
            {"trade_date": date(2026, 3, 5), "close": 140.0},
        ]
    }

    run_summary, symbol_rows = engine.run(signals=signals, prices_by_symbol=prices)

    assert run_summary["total_samples"] == 2
    assert run_summary["evaluated_samples"] == 2
    assert run_summary["skipped_count"] == 0
    assert run_summary["direction_hit_rate"] == 0.5
    assert run_summary["win_rate"] == 0.5
    assert run_summary["avg_return"] == 0.009091
    assert run_summary["max_drawdown"] == -0.181818

    assert len(symbol_rows) == 1
    assert symbol_rows[0]["symbol"] == "US:QQQ"
    assert symbol_rows[0]["direction_hit_rate"] == 0.5


def test_backtest_engine_skips_when_no_future_window() -> None:
    engine = BacktestEngine(eval_window_days=20)
    signals = [{"symbol": "US:QQQ", "trade_date": date(2026, 3, 5), "action": "buy"}]
    prices = {
        "US:QQQ": [
            {"trade_date": date(2026, 3, 5), "close": 140.0},
            {"trade_date": date(2026, 3, 6), "close": 142.0},
        ]
    }

    run_summary, symbol_rows = engine.run(signals=signals, prices_by_symbol=prices)

    assert run_summary["total_samples"] == 1
    assert run_summary["evaluated_samples"] == 0
    assert run_summary["skipped_count"] == 1
    assert run_summary["direction_hit_rate"] is None
    assert symbol_rows[0]["skipped_count"] == 1
