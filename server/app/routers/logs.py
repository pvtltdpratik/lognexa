from datetime import datetime
from math import ceil
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.errors import APIError
from app.models import AccessLog, Alert, RiskScore, User
from app.schemas import (
    AccessLogDetail,
    AccessLogOut,
    Action,
    AlertBrief,
    LogStatus,
    Page,
    RiskScoreOut,
    Sensitivity,
    Severity,
    UserOut,
)

router = APIRouter(prefix="/logs", tags=["logs"])


def log_out(log: AccessLog, username: str, risk: RiskScore | None, has_alert: bool) -> AccessLogOut:
    return AccessLogOut(
        id=log.id, user_id=log.user_id, username=username, timestamp=log.timestamp,
        ip_address=log.ip_address, country=log.country, city=log.city, device=log.device,
        action=log.action, resource=log.resource, resource_sensitivity=log.resource_sensitivity,
        status=log.status, risk_score=risk.risk_score if risk else None,
        severity=risk.severity if risk else None, has_alert=has_alert,
    )


@router.get("", response_model=Page[AccessLogOut], summary="List access logs with filters")
def list_logs(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100, description="Username, IP, resource or city"),
    user_id: int | None = Query(None, ge=1),
    action: Action | None = None,
    status: LogStatus | None = None,
    sensitivity: Sensitivity | None = None,
    severity: Severity | None = None,
    min_risk: float | None = Query(None, ge=0, le=100),
    has_alert: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    sort: Literal["timestamp_desc", "timestamp_asc", "risk_desc"] = "timestamp_desc",
    db: Session = Depends(get_db),
):
    if start and end and end < start:
        raise APIError(422, "validation_error", "end must not be earlier than start",
                       [{"field": "end", "message": "end must not be earlier than start"}])

    q = (
        select(AccessLog, User.username, RiskScore, Alert.id)
        .join(User, User.id == AccessLog.user_id)
        .outerjoin(RiskScore, RiskScore.log_id == AccessLog.id)
        .outerjoin(Alert, Alert.log_id == AccessLog.id)
    )
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(User.username).like(like), func.lower(AccessLog.ip_address).like(like),
            func.lower(AccessLog.resource).like(like), func.lower(AccessLog.city).like(like),
        ))
    if user_id:
        q = q.where(AccessLog.user_id == user_id)
    if action:
        q = q.where(AccessLog.action == action)
    if status:
        q = q.where(AccessLog.status == status)
    if sensitivity:
        q = q.where(AccessLog.resource_sensitivity == sensitivity)
    if severity:
        q = q.where(RiskScore.severity == severity)
    if min_risk is not None:
        q = q.where(RiskScore.risk_score >= min_risk)
    if has_alert is not None:
        q = q.where(Alert.id.is_not(None) if has_alert else Alert.id.is_(None))
    if start:
        q = q.where(AccessLog.timestamp >= start)
    if end:
        q = q.where(AccessLog.timestamp <= end)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = {
        "timestamp_desc": [AccessLog.timestamp.desc(), AccessLog.id.desc()],
        "timestamp_asc": [AccessLog.timestamp.asc(), AccessLog.id.asc()],
        "risk_desc": [RiskScore.risk_score.desc().nulls_last(), AccessLog.timestamp.desc()],
    }[sort]
    rows = db.execute(q.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return Page[AccessLogOut](
        items=[log_out(log, username, risk, alert_id is not None) for log, username, risk, alert_id in rows],
        total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{log_id}", response_model=AccessLogDetail, summary="Log detail with risk explanation")
def get_log(log_id: int = Path(ge=1), db: Session = Depends(get_db)):
    log = db.scalar(
        select(AccessLog)
        .options(selectinload(AccessLog.user), selectinload(AccessLog.risk), selectinload(AccessLog.alert))
        .where(AccessLog.id == log_id)
    )
    if not log:
        raise APIError(404, "not_found", f"Access log {log_id} does not exist")
    base = log_out(log, log.user.username, log.risk, log.alert is not None)
    return AccessLogDetail(
        **base.model_dump(),
        injected_anomaly=log.injected_anomaly,
        user=UserOut.model_validate(log.user),
        risk=RiskScoreOut.model_validate(log.risk) if log.risk else None,
        alert=AlertBrief.model_validate(log.alert) if log.alert else None,
    )
