"""initial schema

Revision ID: 20260309_0001
Revises:
Create Date: 2026-03-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etf_instruments",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=12), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("benchmark_index", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_table(
        "index_proxy_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_symbol", sa.String(length=32), nullable=False),
        sa.Column("proxy_symbol", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "etf_daily_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("pct_chg", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "trade_date", name="uq_etf_daily_symbol_date"),
    )
    op.create_index("ix_etf_daily_bars_symbol", "etf_daily_bars", ["symbol"])
    op.create_index("ix_etf_daily_bars_trade_date", "etf_daily_bars", ["trade_date"])

    op.create_table(
        "etf_realtime_quotes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quote_time", sa.DateTime(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("turnover", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_etf_realtime_quotes_symbol", "etf_realtime_quotes", ["symbol"])
    op.create_index(
        "ix_etf_realtime_quotes_quote_time", "etf_realtime_quotes", ["quote_time"]
    )

    op.create_table(
        "analysis_tasks",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("symbols_json", sa.Text(), nullable=False),
        sa.Column("force_refresh", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"])

    op.create_table(
        "etf_analysis_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("trend", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("factors_json", sa.Text(), nullable=False),
        sa.Column("key_points_json", sa.Text(), nullable=False),
        sa.Column("risk_alerts_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_etf_analysis_reports_task_id", "etf_analysis_reports", ["task_id"]
    )
    op.create_index(
        "ix_etf_analysis_reports_symbol", "etf_analysis_reports", ["symbol"]
    )
    op.create_index(
        "ix_etf_analysis_reports_trade_date", "etf_analysis_reports", ["trade_date"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_etf_analysis_reports_trade_date", table_name="etf_analysis_reports"
    )
    op.drop_index("ix_etf_analysis_reports_symbol", table_name="etf_analysis_reports")
    op.drop_index("ix_etf_analysis_reports_task_id", table_name="etf_analysis_reports")
    op.drop_table("etf_analysis_reports")
    op.drop_index("ix_analysis_tasks_status", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")
    op.drop_index("ix_etf_realtime_quotes_quote_time", table_name="etf_realtime_quotes")
    op.drop_index("ix_etf_realtime_quotes_symbol", table_name="etf_realtime_quotes")
    op.drop_table("etf_realtime_quotes")
    op.drop_index("ix_etf_daily_bars_trade_date", table_name="etf_daily_bars")
    op.drop_index("ix_etf_daily_bars_symbol", table_name="etf_daily_bars")
    op.drop_table("etf_daily_bars")
    op.drop_table("index_proxy_mappings")
    op.drop_table("etf_instruments")
