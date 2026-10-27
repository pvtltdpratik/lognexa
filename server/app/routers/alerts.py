from datetime import datetime
from math import ceil
from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.errors import APIError
from app.models import AccessLog, Alert, Device, EndpointEvent, User
from app.routers.logs import log_out
from app.schemas import AlertDetail, AlertOut, AlertSource, AlertStatus, AlertUpdate, Page, RiskScoreOut, Severity
from app.security import Principal, optional_principal

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _endpoint_summary(ev: EndpointEvent | None) -> str:
    if ev is None:
        return "endpoint event"
    detail = ev.process_name or ev.file_path or (f"{ev.dst_ip}:{ev.dst_port}" if ev.dst_ip else None) or ev.source
    return f"{ev.event_type} · {detail}"[:200]


def alert_out(alert: Alert) -> AlertOut:
    common = dict(
        id=alert.id, source=alert.source, log_id=alert.log_id, user_id=alert.user_id,
        device_id=alert.device_id, endpoint_event_id=alert.endpoint_event_id, event_count=alert.event_count or 1,
        correlation_key=alert.correlation_key, severity=alert.severity, risk_score=alert.risk_score,
        title=alert.title, description=alert.description, status=alert.status,
        resolution_note=alert.resolution_note, resolved_by=alert.resolved_by, resolved_at=alert.resolved_at,
        created_at=alert.created_at, updated_at=alert.updated_at,
    )
    if alert.source == "endpoint":
        ev, dev = alert.endpoint_event, alert.device
        return AlertOut(
            **common, hostname=dev.hostname if dev else None, os_type=dev.os_type if dev else None,
            username=(ev.username if ev and ev.username else (dev.hostname if dev else "unknown")),
            timestamp=ev.timestamp if ev else alert.created_at, resource=_endpoint_summary(ev),
            ip_address=(ev.src_ip or ev.dst_ip) if ev else (dev.ip_address if dev else None),
        )
    return AlertOut(
        **common, username=alert.user.username, timestamp=alert.log.timestamp,
        resource=alert.log.resource, ip_address=alert.log.ip_address,
    )


def _load(db: Session, alert_id: int, principal: Principal | None) -> Alert:
    alert = db.scalar(
        select(Alert)
        .options(
            selectinload(Alert.user), selectinload(Alert.log).selectinload(AccessLog.risk),
            selectinload(Alert.device), selectinload(Alert.endpoint_event),
        )
        .where(Alert.id == alert_id)
    )
    if not alert:
        raise APIError(404, "not_found", f"Alert {alert_id} does not exist")
    if alert.source == "endpoint" and principal is None:
        # Endpoint telemetry is sensitive: require an analyst/admin token.
        raise APIError(401, "authentication_required", "Sign in with an analyst or admin token to view endpoint alerts")
    return alert


@router.get("", response_model=Page[AlertOut], summary="List alerts")
def list_alerts(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(20, ge=1, le=100),
    status: AlertStatus | None = None,
    severity: Severity | None = None,
    source: AlertSource | None = Query(None, description="access_log or endpoint (endpoint requires a token)"),
    user_id: int | None = Query(None, ge=1),
    device_id: int | None = Query(None, ge=1),
    search: str | None = Query(None, min_length=1, max_length=100),
    sort: Literal["newest", "oldest", "risk_desc"] = "risk_desc",
    db: Session = Depends(get_db),
    principal: Principal | None = Depends(optional_principal),
):
    if principal is None:
        if source == "endpoint" or device_id:
            raise APIError(401, "authentication_required", "Sign in with an analyst or admin token to view endpoint alerts")
        source = "access_log"  # unauthenticated callers keep the v1 behaviour

    event_time = func.coalesce(AccessLog.timestamp, EndpointEvent.timestamp, Alert.created_at)
    q = (
        select(Alert)
        .outerjoin(User, User.id == Alert.user_id)
        .outerjoin(AccessLog, AccessLog.id == Alert.log_id)
        .outerjoin(Device, Device.id == Alert.device_id)
        .outerjoin(EndpointEvent, EndpointEvent.id == Alert.endpoint_event_id)
        .options(selectinload(Alert.user), selectinload(Alert.log), selectinload(Alert.device), selectinload(Alert.endpoint_event))
    )
    if source:
        q = q.where(Alert.source == source)
    if status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    if user_id:
        q = q.where(Alert.user_id == user_id)
    if device_id:
        q = q.where(Alert.device_id == device_id)
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(User.username).like(like), func.lower(Alert.title).like(like),
            func.lower(AccessLog.resource).like(like), func.lower(AccessLog.ip_address).like(like),
            func.lower(Device.hostname).like(like), func.lower(EndpointEvent.username).like(like),
            func.lower(EndpointEvent.process_name).like(like),
        ))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = {
        "newest": [event_time.desc()],
        "oldest": [event_time.asc()],
        "risk_desc": [Alert.risk_score.desc(), event_time.desc()],
    }[sort]
    alerts = db.scalars(q.order_by(*order, Alert.id).offset((page - 1) * page_size).limit(page_size)).all()
    return Page[AlertOut](
        items=[alert_out(a) for a in alerts], total=total, page=page, page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{alert_id}", response_model=AlertDetail, summary="Alert detail")
def get_alert(
    alert_id: int = Path(ge=1), db: Session = Depends(get_db),
    principal: Principal | None = Depends(optional_principal),
):
    alert = _load(db, alert_id, principal)
    if alert.source == "endpoint":
        from app.routers.endpoints import _alert_map, _event_out

        ids = sorted(set(alert.related_event_ids or []) | ({alert.endpoint_event_id} - {None}))
        events = db.scalars(select(EndpointEvent).where(EndpointEvent.id.in_(ids)).order_by(EndpointEvent.timestamp)).all()
        host = alert.device.hostname if alert.device else "unknown"
        amap = _alert_map(db, {alert.device_id} if alert.device_id else set())
        primary = next((e for e in events if e.id == alert.endpoint_event_id), None)
        return AlertDetail(
            **alert_out(alert).model_dump(),
            endpoint_event=(
                _event_out(primary, host, amap).model_dump(mode="json")
                | {"triggered_rules": primary.triggered_rules or [], "explanation": primary.explanation,
                   "rule_score": primary.rule_score, "ml_score": primary.ml_score, "ml_is_anomaly": primary.ml_is_anomaly}
                if primary else None
            ),
            related_events=[_event_out(e, host, amap).model_dump(mode="json") for e in events],
        )
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
    principal: Principal | None = Depends(optional_principal),
):
    alert = _load(db, alert_id, principal)
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
