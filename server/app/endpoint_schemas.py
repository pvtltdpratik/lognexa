"""Pydantic schemas for endpoint monitoring (agents, devices, telemetry)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import ORM, Severity

OsType = Literal["windows", "linux"]
Category = Literal["authentication", "process", "network", "file", "persistence", "system", "agent"]
CollectorStatus = Literal["ok", "unsupported", "permission_denied", "error", "disabled"]
Connection = Literal["online", "stale", "offline", "never", "revoked"]

MAX_RAW_BYTES = 16_384


def _naive_utc(v: datetime) -> datetime:
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v.replace(microsecond=0)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- agent -> server -------------------------------------------------------------------
class EnrollRequest(Strict):
    token: str = Field(min_length=20, max_length=200)
    hostname: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    os_type: OsType
    os_version: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(pattern=r"^\d+\.\d+\.\d+([-.][A-Za-z0-9]+)?$", max_length=32)
    machine_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9{}_-]+$")


class EnrollResponse(BaseModel):
    device_uid: str
    credential: str = Field(description="Shown once. Store it securely on the endpoint.")
    heartbeat_interval_seconds: int
    max_events_per_batch: int


class CollectorHealth(Strict):
    name: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_]+$")
    status: CollectorStatus
    detail: str | None = Field(None, max_length=300)
    events_collected: int = Field(0, ge=0)
    last_run_at: datetime | None = None


class HeartbeatRequest(Strict):
    agent_version: str = Field(pattern=r"^\d+\.\d+\.\d+([-.][A-Za-z0-9]+)?$", max_length=32)
    os_version: str = Field(min_length=1, max_length=255)
    hostname: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    uptime_seconds: int = Field(ge=0)
    buffer_pending: int = Field(ge=0)
    buffer_total: int = Field(0, ge=0)
    send_failures: int = Field(0, ge=0)
    last_flush_at: datetime | None = None
    is_privileged: bool = False
    collectors: list[CollectorHealth] = Field(default_factory=list, max_length=32)


class HeartbeatResponse(BaseModel):
    status: Literal["ok"]
    server_time: datetime
    heartbeat_interval_seconds: int
    rotate_credentials: bool


class RotateResponse(BaseModel):
    credential: str


class EventIn(Strict):
    event_uid: str = Field(pattern=r"^[0-9a-f]{32,64}$")
    timestamp: datetime
    source: str = Field(pattern=r"^[a-z0-9_]{2,48}$")
    category: Category
    event_type: str = Field(pattern=r"^[a-z0-9_]{2,64}$")
    username: str | None = Field(None, max_length=128)
    process_name: str | None = Field(None, max_length=255)
    process_path: str | None = Field(None, max_length=1024)
    command_line: str | None = Field(None, max_length=8192)
    pid: int | None = Field(None, ge=0, le=2**31 - 1)
    parent_process: str | None = Field(None, max_length=255)
    parent_pid: int | None = Field(None, ge=0, le=2**31 - 1)
    src_ip: str | None = None
    dst_ip: str | None = None
    dst_port: int | None = Field(None, ge=0, le=65535)
    file_path: str | None = Field(None, max_length=2048)
    message: str | None = Field(None, max_length=4096)
    raw: dict | None = None

    _ts = field_validator("timestamp")(lambda cls, v: _naive_utc(v))

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def _ip(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        return str(ip_address(v.strip("[]")))

    @field_validator("raw")
    @classmethod
    def _raw_size(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v, default=str)) > MAX_RAW_BYTES:
            raise ValueError(f"raw must serialise to at most {MAX_RAW_BYTES} bytes")
        return v


class EventBatch(Strict):
    events: list[EventIn] = Field(min_length=1, max_length=5000)


class IngestResult(BaseModel):
    accepted: int
    duplicates: int
    alerts_created: int
    alerts_updated: int


# --- dashboard -------------------------------------------------------------------------
class CollectorHealthOut(BaseModel):
    name: str
    status: CollectorStatus
    detail: str | None = None
    events_collected: int = 0
    last_run_at: datetime | None = None


class DeviceOut(BaseModel):
    id: int
    device_uid: str
    hostname: str
    os_type: OsType
    os_version: str
    agent_version: str
    ip_address: str | None
    status: Literal["active", "revoked"]
    connection: Connection
    enrolled_at: datetime
    last_seen_at: datetime | None
    rotation_requested: bool
    credential_issued_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    collectors: list[CollectorHealthOut]
    buffer_pending: int | None
    is_privileged: bool | None
    events_24h: int
    open_alerts: int
    max_risk_24h: float | None


class HeartbeatOut(BaseModel):
    received_at: datetime
    buffer_pending: int | None
    send_failures: int | None
    collectors_ok: int
    collectors_total: int


class DeviceDetail(DeviceOut):
    heartbeats: list[HeartbeatOut]
    category_counts: dict[str, int]


class DeviceBrief(BaseModel):
    id: int
    hostname: str
    os_type: OsType
    device_uid: str


class EndpointEventOut(BaseModel):
    id: int
    device_id: int
    hostname: str
    os_type: OsType
    timestamp: datetime
    received_at: datetime
    source: str
    category: str
    event_type: str
    username: str | None
    process_name: str | None
    command_line: str | None
    pid: int | None
    src_ip: str | None
    dst_ip: str | None
    dst_port: int | None
    file_path: str | None
    message: str | None
    risk_score: float | None
    severity: Severity | None
    rule_codes: list[str]
    alert_id: int | None


class EndpointEventDetail(EndpointEventOut):
    process_path: str | None
    parent_process: str | None
    parent_pid: int | None
    raw: dict | None
    redacted: bool
    rule_score: float | None
    ml_score: float | None
    ml_is_anomaly: bool | None
    triggered_rules: list[dict]
    explanation: str | None
    device: DeviceBrief
    related: list[EndpointEventOut]


class DeviceRevoke(Strict):
    reason: str = Field(min_length=3, max_length=200)


class EnrollmentTokenCreate(Strict):
    label: str = Field(min_length=2, max_length=80)
    max_uses: int = Field(1, ge=1, le=100)
    expires_in_hours: int = Field(24, ge=1, le=720)


class EnrollmentTokenOut(ORM):
    id: int
    label: str
    token_prefix: str
    max_uses: int
    uses: int
    revoked: bool
    expires_at: datetime
    created_at: datetime


class EnrollmentTokenCreated(EnrollmentTokenOut):
    token: str = Field(description="Plaintext token, shown only once")


class EndpointOverview(BaseModel):
    devices_total: int
    devices_by_os: dict[str, int]
    devices_by_connection: dict[str, int]
    events_24h: int
    events_total: int
    open_endpoint_alerts: int
    severity_counts_24h: dict[str, int]
    category_counts_24h: dict[str, int]
    collector_issues: list[dict]
    hourly: list[dict]


class Me(BaseModel):
    role: Literal["analyst", "admin"]
