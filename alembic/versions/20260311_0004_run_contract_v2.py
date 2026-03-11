"""run contract and v2 schema

Revision ID: 20260311_0004
Revises: 20260311_0003
Create Date: 2026-03-11 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0004"
down_revision = "20260311_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "error_code",
                sa.String(length=64),
                nullable=False,
                server_default="NONE",
            )
        )
    op.create_index(
        "ix_analysis_tasks_run_id",
        "analysis_tasks",
        ["run_id"],
        unique=False,
    )

    with op.batch_alter_table("etf_analysis_reports") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "horizon",
                sa.String(length=32),
                nullable=False,
                server_default="next_trading_day",
            )
        )
        batch_op.add_column(
            sa.Column("rationale", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("degraded", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("fallback_reason", sa.String(length=64), nullable=True)
        )
    op.create_index(
        "ix_etf_analysis_reports_run_id",
        "etf_analysis_reports",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "analysis_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("symbols_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("run_window", sa.String(length=64), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("completed_tasks", sa.Integer(), nullable=False),
        sa.Column("failed_tasks", sa.Integer(), nullable=False),
        sa.Column("cancelled_tasks", sa.Integer(), nullable=False),
        sa.Column("decision_quality_json", sa.Text(), nullable=False),
        sa.Column("failure_summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"], unique=False)
    op.create_index(
        "ix_analysis_runs_run_window",
        "analysis_runs",
        ["run_window"],
        unique=False,
    )

    op.create_table(
        "analysis_run_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_run_audit_logs_run_id",
        "analysis_run_audit_logs",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_run_audit_logs_run_id", table_name="analysis_run_audit_logs")
    op.drop_table("analysis_run_audit_logs")

    op.drop_index("ix_analysis_runs_run_window", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_table("analysis_runs")

    op.drop_index("ix_etf_analysis_reports_run_id", table_name="etf_analysis_reports")
    with op.batch_alter_table("etf_analysis_reports") as batch_op:
        batch_op.drop_column("fallback_reason")
        batch_op.drop_column("degraded")
        batch_op.drop_column("rationale")
        batch_op.drop_column("horizon")
        batch_op.drop_column("run_id")

    op.drop_index("ix_analysis_tasks_run_id", table_name="analysis_tasks")
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.drop_column("error_code")
        batch_op.drop_column("run_id")
