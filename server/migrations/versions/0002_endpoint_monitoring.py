"""Endpoint monitoring: devices, enrolment tokens, heartbeats, telemetry events.

Also extends ``alerts`` so an alert can come from endpoint telemetry:
adds ``source`` (existing rows become 'access_log'), ``device_id``,
``endpoint_event_id``, ``correlation_key``, ``event_count``,
``related_event_ids`` and makes ``log_id`` / ``user_id`` nullable.
No existing rows are deleted or rewritten except for the new defaults.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_uid", sa.String(36), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_type", sa.String(16), nullable=False),
        sa.Column("os_version", sa.String(255), nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=False),
        sa.Column("machine_id", sa.String(128), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("credential_issued_at", sa.DateTime(), nullable=False),
        sa.Column("rotation_requested", sa.Boolean(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("health", sa.JSON(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(200), nullable=True),
        sa.Column(
            "enrollment_token_id", sa.Integer(),
            sa.ForeignKey("enrollment_tokens.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_devices_device_uid", "devices", ["device_uid"], unique=True)
    op.create_index("ix_devices_os_type", "devices", ["os_type"])
    op.create_index("ix_devices_machine_id", "devices", ["machine_id"])
    op.create_index("ix_devices_status", "devices", ["status"])

    op.create_table(
        "device_heartbeats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_device_heartbeats_device_id", "device_heartbeats", ["device_id"])
    op.create_index("ix_device_heartbeats_received_at", "device_heartbeats", ["received_at"])

    op.create_table(
        "endpoint_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_uid", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("os_type", sa.String(16), nullable=False),
        sa.Column("source", sa.String(48), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("process_name", sa.String(255), nullable=True),
        sa.Column("process_path", sa.Text(), nullable=True),
        sa.Column("command_line", sa.Text(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("parent_process", sa.String(255), nullable=True),
        sa.Column("parent_pid", sa.Integer(), nullable=True),
        sa.Column("src_ip", sa.String(45), nullable=True),
        sa.Column("dst_ip", sa.String(45), nullable=True),
        sa.Column("dst_port", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("redacted", sa.Boolean(), nullable=False),
        sa.Column("rule_score", sa.Float(), nullable=True),
        sa.Column("ml_score", sa.Float(), nullable=True),
        sa.Column("ml_is_anomaly", sa.Boolean(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("triggered_rules", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("scored_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("device_id", "event_uid", name="uq_endpoint_events_device_uid"),
    )
    for col in ("device_id", "timestamp", "os_type", "source", "category", "event_type", "username", "risk_score", "severity"):
        op.create_index(f"ix_endpoint_events_{col}", "endpoint_events", [col])
    op.create_index("ix_endpoint_events_device_ts", "endpoint_events", ["device_id", "timestamp"])

    # Extend alerts. Batch mode recreates the table on SQLite (copying every row);
    # on PostgreSQL it issues plain ALTER TABLE statements.
    with op.batch_alter_table("alerts") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=False, server_default="access_log"))
        batch.add_column(sa.Column("device_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("endpoint_event_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("correlation_key", sa.String(160), nullable=True))
        batch.add_column(sa.Column("event_count", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("related_event_ids", sa.JSON(), nullable=True))
        batch.alter_column("log_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key("fk_alerts_device_id", "devices", ["device_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key(
            "fk_alerts_endpoint_event_id", "endpoint_events", ["endpoint_event_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_unique_constraint("uq_alerts_endpoint_event_id", ["endpoint_event_id"])
        batch.create_index("ix_alerts_source", ["source"])
        batch.create_index("ix_alerts_device_id", ["device_id"])
        batch.create_index("ix_alerts_correlation_key", ["correlation_key"])


def downgrade() -> None:
    # Endpoint alerts cannot exist without log_id/user_id in the v1 schema.
    op.execute("DELETE FROM alerts WHERE source = 'endpoint'")
    with op.batch_alter_table("alerts") as batch:
        batch.drop_index("ix_alerts_correlation_key")
        batch.drop_index("ix_alerts_device_id")
        batch.drop_index("ix_alerts_source")
        batch.drop_constraint("uq_alerts_endpoint_event_id", type_="unique")
        batch.drop_constraint("fk_alerts_endpoint_event_id", type_="foreignkey")
        batch.drop_constraint("fk_alerts_device_id", type_="foreignkey")
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("log_id", existing_type=sa.Integer(), nullable=False)
        for col in ("related_event_ids", "event_count", "correlation_key", "endpoint_event_id", "device_id", "source"):
            batch.drop_column(col)
    op.drop_table("endpoint_events")
    op.drop_table("device_heartbeats")
    op.drop_table("devices")
    op.drop_table("enrollment_tokens")
