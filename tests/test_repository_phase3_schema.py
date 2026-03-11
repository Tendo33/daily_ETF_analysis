from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import inspect

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.domain import EtfAnalysisResult
from daily_etf_analysis.repositories.repository import EtfRepository


def _build_repo(tmp_path: Path) -> EtfRepository:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'phase3_schema.db'}")
    return EtfRepository(settings)


def test_phase3_report_columns_present(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    table = inspect(repo.engine).get_columns("etf_analysis_reports")
    column_names = {item["name"] for item in table}

    assert "context_snapshot_json" in column_names
    assert "news_items_json" in column_names
    assert "created_at" in column_names


def test_phase3_backtest_tables_and_repository_roundtrip(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    inspector = inspect(repo.engine)

    assert "backtest_runs" in inspector.get_table_names()
    assert "backtest_results" in inspector.get_table_names()

    run_id = repo.create_backtest_run(
        eval_window_days=20,
        symbols=["US:QQQ"],
        disclaimer="For research only; not investment advice.",
    )
    repo.save_backtest_results(
        run_id=run_id,
        results=[
            {
                "symbol": "US:QQQ",
                "sample_count": 3,
                "evaluated_count": 2,
                "skipped_count": 1,
                "direction_hit_rate": 0.5,
                "avg_return": 0.02,
                "max_drawdown": -0.01,
                "win_rate": 0.5,
            }
        ],
    )

    run = repo.get_backtest_run(run_id)
    assert run is not None
    assert run["eval_window_days"] == 20
    assert run["disclaimer"]

    rows = repo.get_backtest_results(run_id)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "US:QQQ"


def test_phase3_system_config_snapshot_and_audit_roundtrip(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    inspector = inspect(repo.engine)

    assert "system_config_snapshots" in inspector.get_table_names()
    assert "system_config_audit_logs" in inspector.get_table_names()

    version = repo.create_system_config_snapshot(
        config_payload={"etf_list": ["US:QQQ"]},
        actor="admin",
        expected_version=0,
    )
    repo.create_system_config_audit_log(
        version=version,
        actor="admin",
        action="update",
        changes={"etf_list": ["US:QQQ"]},
    )

    latest = repo.get_latest_system_config_snapshot()
    assert latest is not None
    assert latest["version"] == version
    assert latest["config"]["etf_list"] == ["US:QQQ"]

    logs = repo.list_system_config_audit_logs(page=1, limit=20)
    assert len(logs) == 1
    assert logs[0]["version"] == version


def test_phase3_report_context_and_news_roundtrip(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    repo.save_analysis_report(
        task_id="task-1",
        symbol="US:QQQ",
        trade_date=date(2026, 3, 9),
        factors={"return_20": 0.1},
        result=EtfAnalysisResult.neutral_fallback("US:QQQ", "no llm"),
        context_snapshot={"benchmark": "NDX", "force_refresh": False},
        news_items=[{"title": "sample news", "url": "https://example.com"}],
    )

    rows, total = repo.list_history(page=1, limit=20, symbol="US:QQQ")
    assert total == 1
    assert len(rows) == 1

    detail = repo.get_history_record(rows[0]["id"])
    assert detail is not None
    assert detail["context_snapshot"]["benchmark"] == "NDX"

    news = repo.get_history_news(rows[0]["id"])
    assert len(news) == 1
    assert news[0]["title"] == "sample news"


def test_analysis_run_roundtrip(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    repo.create_analysis_run(
        run_id="run-1",
        symbols=["US:QQQ"],
        source="test",
        market="us",
        run_window="us:2026-03-10",
    )
    run = repo.get_analysis_run("run-1")
    assert run is not None
    assert run.run_id == "run-1"
    assert run.market == "us"
    assert run.symbols == ["US:QQQ"]
