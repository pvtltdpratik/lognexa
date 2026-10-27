"""Endpoint telemetry ingest, scoring and alert correlation (database layer)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.endpoint_schemas import EventIn
from app.models import Alert, Device, DeviceHeartbeat, EndpointEvent
from app.services.endpoint_detection import score_endpoint_frame
from app.services.redaction import redact_obj, redact_text
from app.services.scoring import SEVERITY_ORDER

LOOKBACK_DAYS = 14
MAX_CONTEXT_EVENTS = 20_000

EVENT_COLUMNS = [
    "id", "device_id", "timestamp", "category", "event_type", "username", "process_name", "process_path",
    "command_line", "pid", "parent_process", "parent_pid", "src_ip", "dst_ip", "dst_port", "file_path",
    "message", "raw", "source",
]


# --- device status ---------------------------------------------------------------------
def connection_state(device: Device, now: datetime | None = None) -> str:
    if device.status == "revoked":
        return "revoked"
    if device.last_seen_at is None:
        return "never"
    age = ((now or datetime.utcnow()) - device.last_seen_at).total_seconds()
    s = get_settings()
    if age <= s.stale_after_seconds:
        return "online"
    if age <= s.offline_after_seconds:
        return "stale"
    return "offline"


def record_heartbeat(db: Session, device: Device, payload: dict) -> None:
    now = datetime.utcnow()
    device.health = payload
    device.agent_version = payload.get("agent_version", device.agent_version)
    device.os_version = payload.get("os_version", device.os_version)
    device.hostname = payload.get("hostname", device.hostname)
    db.add(DeviceHeartbeat(device_id=device.id, received_at=now, payload=payload))
    db.flush()
    keep = get_settings().heartbeats_kept_per_device
    cutoff_id = db.scalar(
        select(DeviceHeartbeat.id).where(DeviceHeartbeat.device_id == device.id)
        .order_by(DeviceHeartbeat.id.desc()).offset(keep).limit(1)
    )
    if cutoff_id is not None:
        db.execute(delete(DeviceHeartbeat).where(DeviceHeartbeat.device_id == device.id, DeviceHeartbeat.id <= cutoff_id))


# --- ingest ----------------------------------------------------------------------------
def ingest_events(db: Session, device: Device, events: list[EventIn]) -> dict:
    """Store new events (deduplicated on event_uid), score them, raise alerts."""
    uids = list({e.event_uid for e in events})
    existing = set(
        db.scalars(select(EndpointEvent.event_uid).where(EndpointEvent.device_id == device.id, EndpointEvent.event_uid.in_(uids)))
    )
    now = datetime.utcnow()
    new_rows, seen = [], set()
    for e in events:
        if e.event_uid in existing or e.event_uid in seen:
            continue
        seen.add(e.event_uid)
        cmd, c1 = redact_text(e.command_line)
        msg, c2 = redact_text(e.message)
        raw, c3 = redact_obj(e.raw) if e.raw else (None, False)
        new_rows.append(
            EndpointEvent(
                device_id=device.id, event_uid=e.event_uid, timestamp=e.timestamp, received_at=now,
                os_type=device.os_type, source=e.source, category=e.category, event_type=e.event_type,
                username=e.username, process_name=e.process_name, process_path=e.process_path,
                command_line=cmd, pid=e.pid, parent_process=e.parent_process, parent_pid=e.parent_pid,
                src_ip=e.src_ip, dst_ip=e.dst_ip, dst_port=e.dst_port, file_path=e.file_path,
                message=msg, raw=raw, redacted=c1 or c2 or c3,
            )
        )
    db.add_all(new_rows)
    db.flush()
    created = updated = 0
    if new_rows:
        created, updated = score_device(db, device, only_ids={r.id for r in new_rows})
    return {"accepted": len(new_rows), "duplicates": len(events) - len(new_rows), "alerts_created": created, "alerts_updated": updated}


# --- scoring ---------------------------------------------------------------------------
def _load_device_frame(db: Session, device_id: int) -> pd.DataFrame:
    since = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    cols = [getattr(EndpointEvent, c) for c in EVENT_COLUMNS]
    rows = db.execute(
        select(*cols).where(EndpointEvent.device_id == device_id, EndpointEvent.timestamp >= since)
        .order_by(EndpointEvent.timestamp.desc()).limit(MAX_CONTEXT_EVENTS)
    ).all()
    return pd.DataFrame([r._asdict() for r in rows], columns=EVENT_COLUMNS)


def score_device(db: Session, device: Device, only_ids: set[int] | None = None, rule_weight: float = 0.6) -> tuple[int, int]:
    """Score a device's events using its look-back window as context.

    ``only_ids`` limits which events are (re)written; ``None`` rescoring all.
    Returns (alerts created, alerts updated)."""
    df = _load_device_frame(db, device.id)
    if df.empty:
        return 0, 0
    scored = score_endpoint_frame(df, rule_weight=rule_weight, seed=get_settings().random_seed)
    if only_ids is not None:
        scored = scored[scored["id"].isin(only_ids)]
    now = datetime.utcnow()
    by_id = {e.id: e for e in db.scalars(select(EndpointEvent).where(EndpointEvent.id.in_(scored["id"].tolist())))}
    threshold = get_settings().endpoint_alert_threshold
    created = updated = 0
    for row in scored.sort_values("timestamp").itertuples(index=False):
        ev = by_id.get(int(row.id))
        if ev is None:
            continue
        ev.rule_score = float(row.rule_score)
        ev.ml_score = float(row.ml_score)
        ev.ml_is_anomaly = bool(row.ml_is_anomaly)
        ev.risk_score = float(row.risk_score)
        ev.severity = row.severity
        ev.triggered_rules = row.triggered_rules
        ev.explanation = row.explanation
        ev.scored_at = now
        if ev.risk_score >= threshold and ev.triggered_rules:
            c, u = _raise_or_correlate(db, device, ev)
            created += c
            updated += u
    db.flush()
    return created, updated


def correlation_key(device: Device, ev: EndpointEvent) -> str:
    entity = ev.username or ev.src_ip or ev.dst_ip or "host"
    return f"dev{device.id}:{entity.lower()}"[:160]


def _already_alerted(db: Session, device: Device, ev: EndpointEvent) -> bool:
    if db.scalar(select(Alert.id).where(Alert.endpoint_event_id == ev.id)):
        return True
    for related in db.scalars(select(Alert.related_event_ids).where(Alert.device_id == device.id, Alert.source == "endpoint")):
        if related and ev.id in related:
            return True
    return False


def _raise_or_correlate(db: Session, device: Device, ev: EndpointEvent) -> tuple[int, int]:
    if _already_alerted(db, device, ev):
        return 0, 0
    key = correlation_key(device, ev)
    window = timedelta(minutes=get_settings().correlation_window_minutes)
    top = max(ev.triggered_rules, key=lambda h: h["points"])
    incident = db.scalar(
        select(Alert).where(
            Alert.source == "endpoint", Alert.correlation_key == key, Alert.status != "resolved",
            Alert.updated_at >= ev.timestamp - window,
        ).order_by(Alert.id.desc()).limit(1)
    )
    # updated_at is server time; compare against the latest correlated event time instead when available.
    if incident is not None:
        last_ids = incident.related_event_ids or []
        last_ts = db.scalar(select(func.max(EndpointEvent.timestamp)).where(EndpointEvent.id.in_(last_ids))) if last_ids else None
        if last_ts is not None and abs((ev.timestamp - last_ts).total_seconds()) > window.total_seconds():
            incident = None
    if incident is not None:
        incident.related_event_ids = sorted(set(incident.related_event_ids or []) | {ev.id})
        incident.event_count = len(incident.related_event_ids)
        if SEVERITY_ORDER[ev.severity] > SEVERITY_ORDER[incident.severity]:
            incident.severity = ev.severity
        if ev.risk_score > incident.risk_score:
            incident.risk_score = ev.risk_score
            incident.endpoint_event_id = ev.id
            incident.title = f"{top['name']} on {device.hostname}"[:160]
        reasons = "; ".join(h["reason"] for h in ev.triggered_rules)
        incident.description = (incident.description + f"\n+ {ev.timestamp:%Y-%m-%d %H:%M:%S} {reasons}")[-8000:]
        incident.updated_at = datetime.utcnow()
        return 0, 1
    db.add(
        Alert(
            source="endpoint", device_id=device.id, endpoint_event_id=ev.id, correlation_key=key,
            event_count=1, related_event_ids=[ev.id], severity=ev.severity, risk_score=ev.risk_score,
            title=f"{top['name']} on {device.hostname}"[:160],
            description=f"{ev.timestamp:%Y-%m-%d %H:%M:%S} {ev.explanation}",
            status="open",
        )
    )
    db.flush()
    return 1, 0


def rescore_all_devices(db: Session, rule_weight: float = 0.6) -> dict:
    created = updated = 0
    devices = db.scalars(select(Device)).all()
    for device in devices:
        c, u = score_device(db, device, None, rule_weight)
        created += c
        updated += u
    db.commit()
    return {"devices": len(devices), "alerts_created": created, "alerts_updated": updated}
