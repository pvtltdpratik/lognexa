"""Endpoints called by Lognexa agents (enrolment, heartbeat, telemetry)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.endpoint_schemas import (
    EnrollRequest,
    EnrollResponse,
    EventBatch,
    HeartbeatRequest,
    HeartbeatResponse,
    IngestResult,
    RotateResponse,
)
from app.errors import APIError
from app.models import Device, EnrollmentToken
from app.security import authenticate_device, client_ip, enforce_agent_transport, hash_secret, issue_device_credential
from app.services.endpoint_service import ingest_events, record_heartbeat

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/enroll", response_model=EnrollResponse, status_code=201, summary="Enrol an endpoint with a one-time token")
def enroll(request: Request, payload: EnrollRequest = Body(...), db: Session = Depends(get_db)):
    enforce_agent_transport(request)
    token = db.scalar(select(EnrollmentToken).where(EnrollmentToken.token_hash == hash_secret(payload.token)))
    now = datetime.utcnow()
    if token is None or token.revoked or token.expires_at < now or token.uses >= token.max_uses:
        # One message for every failure mode so tokens cannot be probed.
        raise APIError(401, "invalid_enrollment_token", "Enrolment token is invalid, expired, revoked or used up")
    token.uses += 1

    # Re-enrolling the same machine replaces its credential but keeps its history.
    device = db.scalar(
        select(Device).where(Device.machine_id == payload.machine_id, Device.os_type == payload.os_type)
        .order_by(Device.id.desc()).limit(1)
    )
    if device is None:
        device = Device(device_uid=str(uuid.uuid4()), machine_id=payload.machine_id, os_type=payload.os_type)
        db.add(device)
    credential, credential_hash = issue_device_credential(device.device_uid)
    device.hostname = payload.hostname
    device.os_version = payload.os_version
    device.agent_version = payload.agent_version
    device.credential_hash = credential_hash
    device.credential_issued_at = now
    device.rotation_requested = False
    device.status = "active"
    device.revoked_at = None
    device.revoked_reason = None
    device.enrollment_token_id = token.id
    device.last_seen_at = now
    device.ip_address = (client_ip(request) or "")[:45] or None
    db.commit()
    s = get_settings()
    return EnrollResponse(
        device_uid=device.device_uid, credential=credential,
        heartbeat_interval_seconds=s.heartbeat_interval_seconds, max_events_per_batch=s.max_events_per_batch,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse, summary="Report agent health")
def heartbeat(payload: HeartbeatRequest = Body(...), device: Device = Depends(authenticate_device), db: Session = Depends(get_db)):
    record_heartbeat(db, device, payload.model_dump(mode="json"))
    db.commit()
    s = get_settings()
    return HeartbeatResponse(
        status="ok", server_time=datetime.utcnow(),
        heartbeat_interval_seconds=s.heartbeat_interval_seconds, rotate_credentials=device.rotation_requested,
    )


@router.post("/events", response_model=IngestResult, summary="Upload a batch of telemetry events")
def upload_events(batch: EventBatch = Body(...), device: Device = Depends(authenticate_device), db: Session = Depends(get_db)):
    limit = get_settings().max_events_per_batch
    if len(batch.events) > limit:
        raise APIError(413, "batch_too_large", f"At most {limit} events per batch")
    result = ingest_events(db, device, batch.events)
    db.commit()
    return IngestResult(**result)


@router.post("/rotate-credentials", response_model=RotateResponse, summary="Exchange the current credential for a new one")
def rotate(device: Device = Depends(authenticate_device), db: Session = Depends(get_db)):
    credential, credential_hash = issue_device_credential(device.device_uid)
    device.credential_hash = credential_hash
    device.credential_issued_at = datetime.utcnow()
    device.rotation_requested = False
    db.commit()
    return RotateResponse(credential=credential)
