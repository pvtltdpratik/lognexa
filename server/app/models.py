"""ORM models.

Access-log auditing: users, access_logs, risk_scores, alerts, analysis_runs.
Endpoint monitoring: enrollment_tokens, devices, device_heartbeats, endpoint_events.
Schema changes are applied with Alembic migrations (server/migrations).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    department: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64))
    home_country: Mapped[str] = mapped_column(String(2))
    home_city: Mapped[str] = mapped_column(String(64))
    shift: Mapped[str] = mapped_column(String(16), default="day")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    logs: Mapped[list["AccessLog"]] = relationship(back_populates="user")


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str] = mapped_column(String(64))
    device: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32), index=True)
    resource: Mapped[str] = mapped_column(String(160))
    resource_sensitivity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # Ground-truth label written by the synthetic generator. It is NEVER used as a
    # detection input; it only exists so detection quality can be evaluated.
    injected_anomaly: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped[User] = relationship(back_populates="logs")
    risk: Mapped["RiskScore | None"] = relationship(
        back_populates="log", uselist=False, cascade="all, delete-orphan"
    )
    alert: Mapped["Alert | None"] = relationship(
        back_populates="log", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_access_logs_user_ts", "user_id", "timestamp"),)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    logs_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    alerts_created: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("access_logs.id", ondelete="CASCADE"), unique=True, index=True
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    rule_score: Mapped[float] = mapped_column(Float)
    ml_score: Mapped[float] = mapped_column(Float)
    ml_is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    triggered_rules: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    top_features: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    log: Mapped[AccessLog] = relationship(back_populates="risk")


class Alert(Base):
    """Alert raised from an access log (``source='access_log'``) or from endpoint
    telemetry (``source='endpoint'``). Endpoint alerts group correlated events
    into one incident via ``correlation_key``."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(
        String(16), default="access_log", server_default="access_log", index=True
    )
    log_id: Mapped[int | None] = mapped_column(
        ForeignKey("access_logs.id", ondelete="CASCADE"), unique=True, index=True, nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=True
    )
    endpoint_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("endpoint_events.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    correlation_key: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    related_event_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(16), index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    log: Mapped[AccessLog | None] = relationship(back_populates="alert")
    user: Mapped[User | None] = relationship()
    device: Mapped["Device | None"] = relationship()
    endpoint_event: Mapped["EndpointEvent | None"] = relationship(foreign_keys=[endpoint_event_id])


# --- endpoint monitoring -----------------------------------------------------------


class EnrollmentToken(Base):
    """Limited-use secret an administrator hands to an agent for enrolment.

    Only a SHA-256 hash is stored; the plaintext is shown once at creation."""

    __tablename__ = "enrollment_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_prefix: Mapped[str] = mapped_column(String(12))
    label: Mapped[str] = mapped_column(String(80))
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Device(Base):
    """An enrolled endpoint running the Lognexa agent."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_uid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    os_type: Mapped[str] = mapped_column(String(16), index=True)
    os_version: Mapped[str] = mapped_column(String(255))
    agent_version: Mapped[str] = mapped_column(String(32))
    machine_id: Mapped[str] = mapped_column(String(128), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # SHA-256 of the per-device secret; the secret itself is never stored.
    credential_hash: Mapped[str] = mapped_column(String(64))
    credential_issued_at: Mapped[datetime] = mapped_column(DateTime)
    rotation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    health: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enrollment_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("enrollment_tokens.id", ondelete="SET NULL"), nullable=True
    )


class DeviceHeartbeat(Base):
    """Health snapshots reported by agents (pruned to the most recent per device)."""

    __tablename__ = "device_heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EndpointEvent(Base):
    """Normalised telemetry event collected by an agent.

    ``event_uid`` is a content hash computed by the agent and
    ``(device_id, event_uid)`` is unique, so re-sent batches are deduplicated."""

    __tablename__ = "endpoint_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    event_uid: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    os_type: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(48), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    process_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    command_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_process: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    src_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    dst_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    dst_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Detection results (null until scored)
    rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_is_anomaly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    triggered_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device: Mapped[Device] = relationship()

    __table_args__ = (
        UniqueConstraint("device_id", "event_uid", name="uq_endpoint_events_device_uid"),
        Index("ix_endpoint_events_device_ts", "device_id", "timestamp"),
    )
