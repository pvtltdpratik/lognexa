"""Baseline: access-log auditing schema (v1.0.0).

Creates the five original tables exactly as v1.0.0 created them with
``Base.metadata.create_all``. Databases that already contain these tables are
stamped at this revision instead of running it (see app/migrations.py), so
existing data is never touched.

Revision ID: 0001
Revises:
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(160), nullable=False, unique=True),
        sa.Column("department", sa.String(64), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("home_country", sa.String(2), nullable=False),
        sa.Column("home_city", sa.String(64), nullable=False),
        sa.Column("shift", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_department", "users", ["department"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("logs_analyzed", sa.Integer(), nullable=False),
        sa.Column("alerts_created", sa.Integer(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )

    op.create_table(
        "access_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("device", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("resource", sa.String(160), nullable=False),
        sa.Column("resource_sensitivity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("injected_anomaly", sa.String(32), nullable=True),
    )
    op.create_index("ix_access_logs_user_id", "access_logs", ["user_id"])
    op.create_index("ix_access_logs_timestamp", "access_logs", ["timestamp"])
    op.create_index("ix_access_logs_action", "access_logs", ["action"])
    op.create_index("ix_access_logs_resource_sensitivity", "access_logs", ["resource_sensitivity"])
    op.create_index("ix_access_logs_status", "access_logs", ["status"])
    op.create_index("ix_access_logs_user_ts", "access_logs", ["user_id", "timestamp"])

    op.create_table(
        "risk_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("access_logs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_score", sa.Float(), nullable=False),
        sa.Column("ml_score", sa.Float(), nullable=False),
        sa.Column("ml_is_anomaly", sa.Boolean(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("triggered_rules", sa.JSON(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("top_features", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_risk_scores_log_id", "risk_scores", ["log_id"], unique=True)
    op.create_index("ix_risk_scores_risk_score", "risk_scores", ["risk_score"])
    op.create_index("ix_risk_scores_severity", "risk_scores", ["severity"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("access_logs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(80), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_log_id", "alerts", ["log_id"], unique=True)
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_status", "alerts", ["status"])


def downgrade() -> None:
    for table in ("alerts", "risk_scores", "access_logs", "analysis_runs", "users"):
        op.drop_table(table)
