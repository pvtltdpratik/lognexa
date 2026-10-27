"""Dashboard APIs for endpoint monitoring (analyst / admin only)."""

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.endpoint_schemas import (
    Category,
    CollectorHealthOut,
    Connection,
    DeviceBrief,
    DeviceDetail,
    DeviceOut,
    DeviceRevoke,
    EndpointEventDetail,
    EndpointEventOut,
    EndpointOverview,
    EnrollmentTokenCreate,
    EnrollmentTokenCreated,
    EnrollmentTokenOut,
    HeartbeatOut,
    Me,
    OsType,
)
from app.errors import APIError
from app.models import Alert, Device, DeviceHeartbeat, EndpointEvent, EnrollmentToken
from app.schemas import Page, Severity
from app.security import Principal, hash_secret, new_secret, require_admin, require_analyst
from app.services.endpoint_service import connection_state

router = APIRouter(tags=["endpoints"])

SEVERITIES = ["low", "medium", "high", "critical"]


@router.get("/auth/me", response_model=Me, summary="Role of the presented token")
def me(principal: Principal = Depends(require_analyst)):
    return Me(role=principal.role)


# --- devices -----------------------------------------------------------------------------
def _device_out(db: Session, d: Device, now: datetime) -> dict:
    since = now - timedelta(hours=24)
    events_24h, max_risk = db.execute(
        select(func.count(EndpointEvent.id), func.max(EndpointEvent.risk_score))
        .where(EndpointEvent.device_id == d.id, EndpointEvent.timestamp >= since)
    ).one()
    open_alerts = db.scalar(
        select(func.count(Alert.id)).where(Alert.device_id == d.id, Alert.status != "resolved")
    ) or 0
    health = d.health or {}
    return dict(
        id=d.id, device_uid=d.device_uid, hostname=d.hostname, os_type=d.os_type, os_version=d.os_version,
        agent_version=d.agent_version, ip_address=d.ip_address, status=d.status,
        connection=connection_state(d, now), enrolled_at=d.enrolled_at, last_seen_at=d.last_seen_at,
        rotation_requested=d.rotation_requested, credential_issued_at=d.credential_issued_at,
        revoked_at=d.revoked_at, revoked_reason=d.revoked_reason,
        collectors=[CollectorHealthOut(**c) for c in health.get("collectors", [])],
        buffer_pending=health.get("buffer_pending"), is_privileged=health.get("is_privileged"),
        events_24h=events_24h or 0, open_alerts=open_alerts, max_risk_24h=max_risk,
    )


def _get_device(db: Session, device_id: int) -> Device:
    d = db.get(Device, device_id)
    if not d:
        raise APIError(404, "not_found", f"Device {device_id} does not exist")
    return d


@router.get("/devices", response_model=list[DeviceOut], summary="Endpoint inventory")
def list_devices(
    os_type: OsType | None = None,
    connection: Connection | None = None,
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_analyst),
):
    q = select(Device).order_by(Device.hostname)
    if os_type:
        q = q.where(Device.os_type == os_type)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(func.lower(Device.hostname).like(like), func.lower(Device.ip_address).like(like), func.lower(Device.os_version).like(like)))
    now = datetime.utcnow()
    items = [_device_out(db, d, now) for d in db.scalars(q)]
    if connection:
        items = [i for i in items if i["connection"] == connection]
    return items


@router.get("/devices/{device_id}", response_model=DeviceDetail, summary="Device detail and health history")
def get_device(device_id: int = Path(ge=1), db: Session = Depends(get_db), _: Principal = Depends(require_analyst)):
    d = _get_device(db, device_id)
    beats = db.scalars(
        select(DeviceHeartbeat).where(DeviceHeartbeat.device_id == d.id).order_by(DeviceHeartbeat.id.desc()).limit(60)
    ).all()
    cats = dict(
        db.execute(select(EndpointEvent.category, func.count()).where(EndpointEvent.device_id == d.id).group_by(EndpointEvent.category)).all()
    )
    return DeviceDetail(
        **_device_out(db, d, datetime.utcnow()),
        heartbeats=[
            HeartbeatOut(
                received_at=b.received_at, buffer_pending=b.payload.get("buffer_pending"),
                send_failures=b.payload.get("send_failures"),
                collectors_ok=sum(1 for c in b.payload.get("collectors", []) if c.get("status") == "ok"),
                collectors_total=len(b.payload.get("collectors", [])),
            )
            for b in reversed(beats)
        ],
        category_counts=cats,
    )


@router.post("/devices/{device_id}/revoke", response_model=DeviceOut, summary="Revoke a device credential (admin)")
def revoke_device(
    device_id: int = Path(ge=1), payload: DeviceRevoke = Body(...),
    db: Session = Depends(get_db), _: Principal = Depends(require_admin),
):
    d = _get_device(db, device_id)
    if d.status == "revoked":
        raise APIError(409, "no_change", "Device is already revoked")
    d.status = "revoked"
    d.revoked_at = datetime.utcnow()
    d.revoked_reason = payload.reason
    db.commit()
    return _device_out(db, d, datetime.utcnow())


@router.post("/devices/{device_id}/rotate", response_model=DeviceOut, summary="Ask the agent to rotate its credential (admin)")
def request_rotation(device_id: int = Path(ge=1), db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    d = _get_device(db, device_id)
    if d.status == "revoked":
        raise APIError(409, "device_revoked", "Revoked devices must be re-enrolled instead")
    d.rotation_requested = True
    db.commit()
    return _device_out(db, d, datetime.utcnow())


# --- enrolment tokens ------------------------------------------------------------------------
@router.get("/enrollment-tokens", response_model=list[EnrollmentTokenOut], summary="List enrolment tokens (admin)")
def list_tokens(db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    return db.scalars(select(EnrollmentToken).order_by(EnrollmentToken.id.desc()).limit(100)).all()


@router.post("/enrollment-tokens", response_model=EnrollmentTokenCreated, status_code=201, summary="Create an enrolment token (admin)")
def create_token(payload: EnrollmentTokenCreate = Body(...), db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    plaintext = "lnx_" + new_secret(24)
    token = EnrollmentToken(
        token_hash=hash_secret(plaintext), token_prefix=plaintext[:10], label=payload.label,
        max_uses=payload.max_uses, uses=0, revoked=False,
        expires_at=datetime.utcnow() + timedelta(hours=payload.expires_in_hours),
    )
    db.add(token)
    db.commit()
    return EnrollmentTokenCreated(**EnrollmentTokenOut.model_validate(token).model_dump(), token=plaintext)


@router.post("/enrollment-tokens/{token_id}/revoke", response_model=EnrollmentTokenOut, summary="Revoke an enrolment token (admin)")
def revoke_token(token_id: int = Path(ge=1), db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    token = db.get(EnrollmentToken, token_id)
    if not token:
        raise APIError(404, "not_found", f"Enrolment token {token_id} does not exist")
    token.revoked = True
    db.commit()
    return token


# --- events ----------------------------------------------------------------------------------
def _alert_map(db: Session, device_ids: set[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    if not device_ids:
        return out
    for alert_id, primary, related in db.execute(
        select(Alert.id, Alert.endpoint_event_id, Alert.related_event_ids).where(Alert.source == "endpoint", Alert.device_id.in_(device_ids))
    ):
        for eid in (related or []) + ([primary] if primary else []):
            out.setdefault(eid, alert_id)
    return out


def _event_out(ev: EndpointEvent, hostname: str, alerts: dict[int, int]) -> EndpointEventOut:
    return EndpointEventOut(
        id=ev.id, device_id=ev.device_id, hostname=hostname, os_type=ev.os_type, timestamp=ev.timestamp,
        received_at=ev.received_at, source=ev.source, category=ev.category, event_type=ev.event_type,
        username=ev.username, process_name=ev.process_name, command_line=ev.command_line, pid=ev.pid,
        src_ip=ev.src_ip, dst_ip=ev.dst_ip, dst_port=ev.dst_port, file_path=ev.file_path, message=ev.message,
        risk_score=ev.risk_score, severity=ev.severity,
        rule_codes=[h["code"] for h in (ev.triggered_rules or [])], alert_id=alerts.get(ev.id),
    )


def _as_naive_utc(v: datetime | None) -> datetime | None:
    if v is not None and v.tzinfo is not None:
        return v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


@router.get("/endpoint-events", response_model=Page[EndpointEventOut], summary="Endpoint telemetry with filters")
def list_events(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(50, ge=1, le=200),
    device_id: int | None = Query(None, ge=1),
    os_type: OsType | None = None,
    category: Category | None = None,
    severity: Severity | None = None,
    min_risk: float | None = Query(None, ge=0, le=100),
    flagged: bool | None = Query(None, description="Only events with at least one triggered rule"),
    search: str | None = Query(None, min_length=1, max_length=100),
    after_id: int | None = Query(None, ge=0, description="Live polling: only events with a larger id"),
    start: datetime | None = None,
    end: datetime | None = None,
    sort: Literal["newest", "oldest", "risk_desc"] = "newest",
    db: Session = Depends(get_db),
    _: Principal = Depends(require_analyst),
):
    # Stored timestamps are naive UTC; compare like with like (the dashboard sends
    # timezone-aware bounds such as 2026-10-28T00:50:00Z).
    start, end = _as_naive_utc(start), _as_naive_utc(end)
    if start and end and end < start:
        raise APIError(422, "validation_error", "end must not be earlier than start",
                       [{"field": "end", "message": "end must not be earlier than start"}])
    q = select(EndpointEvent, Device.hostname).join(Device, Device.id == EndpointEvent.device_id)
    if device_id:
        q = q.where(EndpointEvent.device_id == device_id)
    if os_type:
        q = q.where(EndpointEvent.os_type == os_type)
    if category:
        q = q.where(EndpointEvent.category == category)
    if severity:
        q = q.where(EndpointEvent.severity == severity)
    if min_risk is not None:
        q = q.where(EndpointEvent.risk_score >= min_risk)
    if flagged:
        q = q.where(EndpointEvent.rule_score > 0)
    if after_id is not None:
        q = q.where(EndpointEvent.id > after_id)
    if start:
        q = q.where(EndpointEvent.timestamp >= start)
    if end:
        q = q.where(EndpointEvent.timestamp <= end)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(*(func.lower(c).like(like) for c in (
            EndpointEvent.username, EndpointEvent.process_name, EndpointEvent.command_line,
            EndpointEvent.file_path, EndpointEvent.dst_ip, EndpointEvent.src_ip, EndpointEvent.message,
            EndpointEvent.event_type, Device.hostname,
        ))))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = {
        "newest": [EndpointEvent.timestamp.desc(), EndpointEvent.id.desc()],
        "oldest": [EndpointEvent.timestamp.asc(), EndpointEvent.id.asc()],
        "risk_desc": [EndpointEvent.risk_score.desc().nulls_last(), EndpointEvent.id.desc()],
    }[sort]
    rows = db.execute(q.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    alerts = _alert_map(db, {ev.device_id for ev, _ in rows})
    return Page[EndpointEventOut](
        items=[_event_out(ev, host, alerts) for ev, host in rows], total=total, page=page,
        page_size=page_size, pages=ceil(total / page_size) if total else 0,
    )


def related_events(db: Session, ev: EndpointEvent, limit: int = 50) -> list[EndpointEvent]:
    """Events on the same device within ±15 minutes sharing a user, IP or process tree."""
    window = timedelta(minutes=15)
    links = []
    if ev.username:
        links.append(EndpointEvent.username == ev.username)
    for ip in {ev.src_ip, ev.dst_ip} - {None}:
        links += [EndpointEvent.src_ip == ip, EndpointEvent.dst_ip == ip]
    if ev.pid:
        links += [EndpointEvent.pid == ev.pid, EndpointEvent.parent_pid == ev.pid]
    if ev.parent_pid:
        links.append(EndpointEvent.pid == ev.parent_pid)
    if not links:
        return []
    return db.scalars(
        select(EndpointEvent).where(
            EndpointEvent.device_id == ev.device_id, EndpointEvent.id != ev.id,
            EndpointEvent.timestamp.between(ev.timestamp - window, ev.timestamp + window), or_(*links),
        ).order_by(EndpointEvent.timestamp).limit(limit)
    ).all()


@router.get("/endpoint-events/{event_id}", response_model=EndpointEventDetail, summary="Event detail with correlated events")
def get_event(event_id: int = Path(ge=1), db: Session = Depends(get_db), _: Principal = Depends(require_analyst)):
    ev = db.get(EndpointEvent, event_id)
    if not ev:
        raise APIError(404, "not_found", f"Endpoint event {event_id} does not exist")
    device = ev.device
    alerts = _alert_map(db, {device.id})
    rel = related_events(db, ev)
    return EndpointEventDetail(
        **_event_out(ev, device.hostname, alerts).model_dump(),
        process_path=ev.process_path, parent_process=ev.parent_process, parent_pid=ev.parent_pid,
        raw=ev.raw, redacted=ev.redacted, rule_score=ev.rule_score, ml_score=ev.ml_score,
        ml_is_anomaly=ev.ml_is_anomaly, triggered_rules=ev.triggered_rules or [], explanation=ev.explanation,
        device=DeviceBrief(id=device.id, hostname=device.hostname, os_type=device.os_type, device_uid=device.device_uid),
        related=[_event_out(r, device.hostname, alerts) for r in rel],
    )


@router.get("/endpoint/overview", response_model=EndpointOverview, summary="Endpoint monitoring statistics")
def endpoint_overview(db: Session = Depends(get_db), _: Principal = Depends(require_analyst)):
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    devices = db.scalars(select(Device)).all()
    by_conn: dict[str, int] = {}
    by_os: dict[str, int] = {}
    issues = []
    for d in devices:
        state = connection_state(d, now)
        by_conn[state] = by_conn.get(state, 0) + 1
        by_os[d.os_type] = by_os.get(d.os_type, 0) + 1
        for c in (d.health or {}).get("collectors", []):
            if c.get("status") not in ("ok", "disabled"):
                issues.append({"device_id": d.id, "hostname": d.hostname, "collector": c.get("name"), "status": c.get("status"), "detail": c.get("detail")})
    sev = dict(db.execute(select(EndpointEvent.severity, func.count()).where(EndpointEvent.timestamp >= since, EndpointEvent.severity.is_not(None)).group_by(EndpointEvent.severity)).all())
    cats = dict(db.execute(select(EndpointEvent.category, func.count()).where(EndpointEvent.timestamp >= since).group_by(EndpointEvent.category)).all())
    hourly = {h: {"hour": (since + timedelta(hours=h + 1)).strftime("%Y-%m-%dT%H:00"), "events": 0, "flagged": 0} for h in range(24)}
    for ts, rule_score in db.execute(select(EndpointEvent.timestamp, EndpointEvent.rule_score).where(EndpointEvent.timestamp >= since)):
        idx = min(23, int((ts - since).total_seconds() // 3600))
        hourly[idx]["events"] += 1
        hourly[idx]["flagged"] += bool(rule_score)
    return EndpointOverview(
        devices_total=len(devices), devices_by_os=by_os, devices_by_connection=by_conn,
        events_24h=sum(cats.values()), events_total=db.scalar(select(func.count(EndpointEvent.id))) or 0,
        open_endpoint_alerts=db.scalar(select(func.count(Alert.id)).where(Alert.source == "endpoint", Alert.status != "resolved")) or 0,
        severity_counts_24h={s: sev.get(s, 0) for s in SEVERITIES}, category_counts_24h=cats,
        collector_issues=issues, hourly=list(hourly.values()),
    )


@router.post("/endpoint/rescore", summary="Re-score all endpoint telemetry (analyst)")
def rescore(
    rule_weight: float = Query(0.6, ge=0, le=1),
    db: Session = Depends(get_db), _: Principal = Depends(require_analyst),
):
    from app.services.endpoint_service import rescore_all_devices

    return rescore_all_devices(db, rule_weight)
