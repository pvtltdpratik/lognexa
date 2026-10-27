"""Pydantic request / response schemas. All API input is validated here."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Severity = Literal["low", "medium", "high", "critical"]
AlertStatus = Literal["open", "acknowledged", "resolved"]
LogStatus = Literal["success", "failure", "denied"]
Action = Literal["login", "logout", "file_read", "file_write", "download", "admin_action"]
Sensitivity = Literal["public", "internal", "confidential", "restricted"]

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- users -----------------------------------------------------------------
class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str
    department: str
    role: str
    home_country: str
    home_city: str
    shift: str


class UserRisk(BaseModel):
    user_id: int
    username: str
    full_name: str
    department: str
    events: int
    avg_risk: float
    max_risk: float
    high_risk_events: int
    open_alerts: int


# --- risk ------------------------------------------------------------------
class TriggeredRule(BaseModel):
    code: str
    name: str
    category: str
    points: int
    reason: str


class TopFeature(BaseModel):
    feature: str
    label: str
    value: float
    z_score: float


class RiskScoreOut(ORM):
    id: int
    log_id: int
    run_id: int
    rule_score: float
    ml_score: float
    ml_is_anomaly: bool
    risk_score: float
    severity: Severity
    triggered_rules: list[TriggeredRule]
    features: dict
    top_features: list[TopFeature]
    explanation: str
    created_at: datetime


class RiskScoreListItem(BaseModel):
    id: int
    log_id: int
    user_id: int
    username: str
    timestamp: datetime
    action: str
    resource: str
    rule_score: float
    ml_score: float
    risk_score: float
    severity: Severity
    rule_codes: list[str]


# --- logs ------------------------------------------------------------------
class AccessLogOut(ORM):
    id: int
    user_id: int
    username: str
    timestamp: datetime
    ip_address: str
    country: str
    city: str
    device: str
    action: str
    resource: str
    resource_sensitivity: str
    status: str
    risk_score: float | None = None
    severity: Severity | None = None
    has_alert: bool = False


class AlertBrief(ORM):
    id: int
    status: AlertStatus
    severity: Severity
    title: str


class AccessLogDetail(AccessLogOut):
    injected_anomaly: str | None = Field(
        None, description="Synthetic ground-truth label (evaluation only, never a detection input)"
    )
    user: UserOut
    risk: RiskScoreOut | None = None
    alert: AlertBrief | None = None


# --- alerts ----------------------------------------------------------------
class AlertOut(ORM):
    id: int
    log_id: int
    user_id: int
    username: str
    severity: Severity
    risk_score: float
    title: str
    description: str
    status: AlertStatus
    resolution_note: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    timestamp: datetime
    resource: str
    ip_address: str


class AlertDetail(AlertOut):
    log: AccessLogOut
    risk: RiskScoreOut | None = None


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: AlertStatus
    resolution_note: str | None = Field(None, max_length=500)
    resolved_by: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _resolution_requirements(self) -> "AlertUpdate":
        if self.status == "resolved":
            if not self.resolution_note or len(self.resolution_note) < 10:
                raise ValueError("resolution_note must be at least 10 characters when resolving an alert")
            if not self.resolved_by or len(self.resolved_by) < 2:
                raise ValueError("resolved_by is required (2-80 characters) when resolving an alert")
        return self


# --- analysis --------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contamination: float = Field(0.05, ge=0.01, le=0.2, description="Expected outlier share for Isolation Forest")
    alert_threshold: float = Field(40.0, ge=1, le=100, description="Minimum risk score that raises an alert")
    rule_weight: float = Field(0.6, ge=0, le=1, description="Weight of the rule score (ML weight = 1 - rule_weight)")


class AnalysisRunOut(ORM):
    id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    logs_analyzed: int
    alerts_created: int
    parameters: dict
    metrics: dict
    error: str | None


class DatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(42, ge=0, le=2**31 - 1)
    n_users: int = Field(60, ge=6, le=500)
    days: int = Field(14, ge=1, le=90)
    n_records: int = Field(2200, ge=200, le=50000)
    run_analysis: bool = True

    @model_validator(mode="after")
    def _enough_records(self) -> "DatasetRequest":
        if self.n_records < self.n_users * 5:
            raise ValueError("n_records must be at least 5 x n_users")
        return self


class DatasetResult(BaseModel):
    users: int
    logs: int
    injected_anomalies: int
    analysis: AnalysisRunOut | None = None


# --- analytics -------------------------------------------------------------
class Overview(BaseModel):
    total_logs: int
    total_users: int
    failed_events: int
    open_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    avg_risk: float
    severity_counts: dict[str, int]
    alert_severity_counts: dict[str, int]
    rule_hits: list[dict]
    daily: list[dict]
    hourly: list[dict]
    top_users: list[UserRisk]
    latest_run: AnalysisRunOut | None
    period_start: datetime | None
    period_end: datetime | None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    database_backend: str
    version: str
    counts: dict[str, int] | None = None
    detail: str | None = None


class DateRange(BaseModel):
    start: datetime | None = None
    end: datetime | None = None

    @field_validator("end")
    @classmethod
    def _order(cls, v, info):
        start = info.data.get("start")
        if v and start and v < start:
            raise ValueError("end must not be earlier than start")
        return v
