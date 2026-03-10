from __future__ import annotations

from pathlib import Path

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.repositories.repository import EtfRepository


def _build_repo(tmp_path: Path) -> EtfRepository:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'backtest_repo.db'}")
    return EtfRepository(settings)


def test_backtest_repository_roundtrip(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    run_id = repo.create_backtest_run(
        eval_window_days=20,
        symbols=["US:QQQ", "CN:159659"],
        disclaimer="For research only; not investment advice.",
    )

    repo.update_backtest_run_summary(
        run_id=run_id,
        total_samples=10,
        evaluated_samples=8,
        skipped_count=2,
        direction_hit_rate=0.625,
        avg_return=0.012,
        max_drawdown=-0.08,
        win_rate=0.5,
    )
    repo.save_backtest_results(
        run_id=run_id,
        results=[
            {
                "symbol": "US:QQQ",
                "sample_count": 5,
                "evaluated_count": 4,
                "skipped_count": 1,
                "direction_hit_rate": 0.75,
                "avg_return": 0.02,
                "max_drawdown": -0.05,
                "win_rate": 0.5,
            }
        ],
    )

    run = repo.get_backtest_run(run_id)
    assert run is not None
    assert run["evaluated_samples"] == 8

    rows = repo.get_backtest_results(run_id)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "US:QQQ"

    symbol = repo.get_backtest_symbol_performance(run_id, "US:QQQ")
    assert symbol is not None
    assert symbol["direction_hit_rate"] == 0.75


def test_backtest_repository_missing_run(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    assert repo.get_backtest_run("missing") is None
    assert repo.get_backtest_symbol_performance("missing", "US:QQQ") is None
