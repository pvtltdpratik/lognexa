from datetime import datetime
from math import ceil
from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.errors import APIError
from app.models import AccessLog, Alert, User
from app.routers.logs import log_out
from app.schemas import AlertDetail, AlertOut, AlertStatus, AlertUpdate, Page, RiskScoreOut, Severity

router = APIRouter(prefix="/alerts", tags=["alerts"])


def alert_out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=alert.id, log_id=alert.log_id, user_id=alert.user_id, username=alert.user.username,
        severity=alert.severity, risk_score=alert.risk_score, title=alert.title,
        description=alert.description, status=alert.status, resolution_note=alert.resolution_note,
        resolved_by=alert.resolved_by, resolved_at=alert.resolved_at, created_at=alert.created_at,
        updated_at=alert.updated_at, timestamp=alert.log.timestamp, resource=alert.log.resource,
        ip_address=alert.log.ip_address,
    )


def _load(db: Session, alert_id: int) -> Alert:
    alert = db.scalar(
        select(Alert)
        .options(selectinload(Alert.user), selectinload(Alert.log).selectinload(AccessLog.risk))
        .where(Alert.id == alert_id)
    )
    if not alert:
        raise APIError(404, "not_found", f"Alert {alert_id} does not exist")
    return alert


@router.get("", response_model=Page[AlertOut], summary="List alerts")
def list_alerts(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(20, ge=1, le=100),
    status: AlertStatus | None = None,
    severity: Severity | None = None,
    user_id: int | None = Query(None, ge=1),
    search: str | None = Query(None, min_length=1, max_length=100),
    sort: Literal["newest", "oldest", "risk_desc"] = "risk_desc",
    db: Session = Depends(get_db),
):
    q = (
        select(Alert)
        .join(User, User.id == Alert.user_id)
        .join(AccessLog, AccessLog.id == Alert.log_id)
        .options(selectinload(Alert.user), selectinload(Alert.log))
    )
    if status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    if user_id:
        q = q.where(Alert.user_id == user_id)
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(User.username).like(like), func.lower(Alert.title).like(like),
            func.lower(AccessLog.resource).like(like), func.lower(AccessLog.ip_address).like(like),
        ))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = {
        "newest": [AccessLog.timestamp.desc()],
        "oldest": [AccessLog.timestamp.asc()],
        "risk_desc": [Alert.risk_score.desc(), AccessLog.timestamp.desc()],
    }[sort]
    alerts = db.scalars(q.order_by(*order, Alert.id).offset((page - 1) * page_size).limit(page_size)).all()
    return Page[AlertOut](
        items=[alert_out(a) for a in alerts], total=total, page=page, page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{alert_id}", response_model=AlertDetail, summary="Alert detail")
def get_alert(alert_id: int = Path(ge=1), db: Session = Depends(get_db)):
    alert = _load(db, alert_id)
    risk = alert.log.risk
    return AlertDetail(
        **alert_out(alert).model_dump(),
        log=log_out(alert.log, alert.user.username, risk, True),
        risk=RiskScoreOut.model_validate(risk) if risk else None,
    )


@router.patch("/{alert_id}", response_model=AlertOut, summary="Acknowledge, resolve or reopen an alert")
def update_alert(
    alert_id: int = Path(ge=1),
    payload: AlertUpdate = Body(...),
    db: Session = Depends(get_db),
):
    alert = _load(db, alert_id)
    if alert.status == payload.status and payload.status != "resolved":
        raise APIError(409, "no_change", f"Alert {alert_id} is already {payload.status}")

    alert.status = payload.status
    if payload.status == "resolved":
        alert.resolution_note = payload.resolution_note
        alert.resolved_by = payload.resolved_by
        alert.resolved_at = datetime.utcnow()
    else:
        alert.resolution_note = payload.resolution_note or None
        alert.resolved_by = None
        alert.resolved_at = None
    alert.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert_out(alert)
