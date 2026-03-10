"""phase3 core tables

Revision ID: 20260310_0002
Revises: 20260309_0001
Create Date: 2026-03-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0002"
down_revision = "20260309_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etf_analysis_reports",
        sa.Column(
            "context_snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "etf_analysis_reports",
        sa.Column("news_items_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "etf_analysis_reports",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("eval_window_days", sa.Integer(), nullable=False),
        sa.Column("symbols_json", sa.Text(), nullable=False),
        sa.Column("total_samples", sa.Integer(), nullable=False),
        sa.Column("evaluated_samples", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("direction_hit_rate", sa.Float(), nullable=True),
        sa.Column("avg_return", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("direction_hit_rate", sa.Float(), nullable=True),
        sa.Column("avg_return", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_run_id", "backtest_results", ["run_id"])
    op.create_index("ix_backtest_results_symbol", "backtest_results", ["symbol"])
    op.create_index("ix_backtest_results_trade_date", "backtest_results", ["trade_date"])
    op.create_index(
        "ix_backtest_results_run_symbol_trade_date",
        "backtest_results",
        ["run_id", "symbol", "trade_date"],
    )

    op.create_table(
        "system_config_snapshots",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )

    op.create_table(
        "system_config_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_system_config_audit_logs_version",
        "system_config_audit_logs",
        ["version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_system_config_audit_logs_version", table_name="system_config_audit_logs"
    )
    op.drop_table("system_config_audit_logs")
    op.drop_table("system_config_snapshots")

    op.drop_index(
        "ix_backtest_results_run_symbol_trade_date", table_name="backtest_results"
    )
    op.drop_index("ix_backtest_results_trade_date", table_name="backtest_results")
    op.drop_index("ix_backtest_results_symbol", table_name="backtest_results")
    op.drop_index("ix_backtest_results_run_id", table_name="backtest_results")
    op.drop_table("backtest_results")
    op.drop_table("backtest_runs")

    op.drop_column("etf_analysis_reports", "created_at")
    op.drop_column("etf_analysis_reports", "news_items_json")
    op.drop_column("etf_analysis_reports", "context_snapshot_json")
