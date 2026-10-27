"""ORM models: users, access_logs, risk_scores, alerts, analysis_runs."""

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
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("access_logs.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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

    log: Mapped[AccessLog] = relationship(back_populates="alert")
    user: Mapped[User] = relationship()
