"""business and security hardening

Revision ID: 20260311_0003
Revises: 20260310_0002
Create Date: 2026-03-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260311_0003"
down_revision = "20260310_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.add_column(sa.Column("skip_reason", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "skipped_symbols_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column(
                "analyzed_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0")
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_etf_analysis_reports_symbol_trade_date_id "
        "ON etf_analysis_reports(symbol, trade_date DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_etf_realtime_quotes_symbol_quote_time "
        "ON etf_realtime_quotes(symbol, quote_time DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_etf_realtime_quotes_symbol_quote_time")
    op.execute("DROP INDEX IF EXISTS ix_etf_analysis_reports_symbol_trade_date_id")

    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.drop_column("skipped_count")
        batch_op.drop_column("analyzed_count")
        batch_op.drop_column("skipped_symbols_json")
        batch_op.drop_column("skip_reason")
