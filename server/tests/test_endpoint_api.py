"""Endpoint API: enrolment, auth, ingest, dedup, detection, alerts, security."""

import hashlib
from datetime import datetime, timedelta, timezone


def _err(resp, status, code):
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["code"] == code
    return resp.json()["error"]


def _event(uid, **kw):
    base = {
        "event_uid": hashlib.sha256(uid.encode()).hexdigest(), "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "test", "category": "system", "event_type": "generic_event",
    }
    base.update(kw)
    return base


# --- authn / authz -------------------------------------------------------------------
def test_endpoints_require_auth(ep_client):
    _err(ep_client.get("/devices"), 401, "authentication_required")
    _err(ep_client.get("/devices", headers={"Authorization": "Bearer wrong"}), 401, "invalid_token")
    _err(ep_client.get("/endpoint/overview"), 401, "authentication_required")


def test_role_enforcement(ep_client):
    # analyst can read, cannot create tokens (admin only)
    assert ep_client.get("/devices", headers=ep_client.analyst).status_code == 200
    _err(ep_client.post("/enrollment-tokens", headers=ep_client.analyst, json={"label": "x"}), 403, "forbidden")
    assert ep_client.get("/auth/me", headers=ep_client.admin).json()["role"] == "admin"


def test_auth_disabled_without_tokens(empty_client):
    """With no tokens configured, endpoint APIs fail closed (503)."""
    import os
    from app.config import get_settings

    saved = {k: os.environ.get(k) for k in ("LOGNEXA_ADMIN_TOKEN", "LOGNEXA_ANALYST_TOKEN")}
    # Empty env values override any server/.env file entry (env > .env in pydantic-settings).
    os.environ["LOGNEXA_ADMIN_TOKEN"] = ""
    os.environ["LOGNEXA_ANALYST_TOKEN"] = ""
    get_settings.cache_clear()
    try:
        _err(empty_client.get("/devices"), 503, "auth_not_configured")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()


# --- enrolment -----------------------------------------------------------------------
def test_enrollment_flow_and_token_limits(ep_client):
    r = ep_client.post("/enrollment-tokens", headers=ep_client.admin,
                       json={"label": "lab", "max_uses": 1, "expires_in_hours": 1})
    assert r.status_code == 201
    token = r.json()["token"]
    assert "token" not in {k.lower() for k in ep_client.get("/enrollment-tokens", headers=ep_client.admin).json()[0]}

    body = {"token": token, "hostname": "enrol-host", "os_type": "linux",
            "os_version": "Ubuntu 24.04", "agent_version": "2.0.0", "machine_id": "ENROL-MACHINE"}
    enr = ep_client.post("/agent/enroll", json=body)
    assert enr.status_code == 201
    assert enr.json()["device_uid"] and "." in enr.json()["credential"]
    # token is now used up
    _err(ep_client.post("/agent/enroll", json=body), 401, "invalid_enrollment_token")


def test_enroll_rejects_bad_input(ep_client):
    _err(ep_client.post("/agent/enroll", json={"token": "short", "hostname": "h", "os_type": "linux",
                                               "os_version": "v", "agent_version": "2.0.0", "machine_id": "MACHINE12"}),
         422, "validation_error")
    _err(ep_client.post("/agent/enroll", json={"token": "x" * 30, "hostname": "h", "os_type": "macos",
                                               "os_version": "v", "agent_version": "2.0.0", "machine_id": "MACHINE12"}),
         422, "validation_error")
    _err(ep_client.post("/agent/enroll", json={"token": "x" * 30, "hostname": "unit-host", "os_type": "linux",
                                               "os_version": "v", "agent_version": "2.0.0", "machine_id": "M12345678", "extra": 1}),
         422, "validation_error")


def test_device_auth_required_for_ingest(ep_client):
    _err(ep_client.post("/agent/events", json={"events": [_event("a")]}), 401, "device_auth_required")
    _err(ep_client.post("/agent/events", headers={"Authorization": "Bearer unknown.secret"}, json={"events": [_event("a")]}),
         401, "invalid_device_credential")


# --- ingest, dedup, detection --------------------------------------------------------
def test_ingest_dedup_and_detection(ep_client, enrolled_device):
    cred, uid, _ = enrolled_device
    events = [_event(f"brute{i:032d}", category="authentication", event_type="logon_failure",
                     username="root", src_ip="198.51.100.9",
                     timestamp=(datetime.now(timezone.utc) - timedelta(minutes=8 - i)).isoformat())
              for i in range(6)]
    events.append(_event("clear" + "0" * 27, category="system", event_type="log_cleared", username="root"))
    r = ep_client.post("/agent/events", headers=cred, json={"events": events})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 7 and body["duplicates"] == 0
    assert body["alerts_created"] >= 1

    # resend -> all duplicates, no new rows
    again = ep_client.post("/agent/events", headers=cred, json={"events": events}).json()
    assert again["accepted"] == 0 and again["duplicates"] == 7

    flagged = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={"flagged": True}).json()
    codes = {c for e in flagged["items"] for c in e["rule_codes"]}
    assert "EP-AUTH-1" in codes and "EP-LOG-1" in codes


def test_batch_limit_enforced(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    # schema allows up to 5000; server batch limit is configurable (default 500)
    big = [_event(f"{i:032d}") for i in range(600)]
    _err(ep_client.post("/agent/events", headers=cred, json={"events": big}), 413, "batch_too_large")
    _err(ep_client.post("/agent/events", headers=cred, json={"events": []}), 422, "validation_error")


def test_redaction_on_ingest(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    ep_client.post("/agent/events", headers=cred, json={"events": [_event(
        "secret" + "0" * 26, category="process", event_type="process_start", process_name="psql",
        command_line="psql 'postgresql://user:Hunter2Password@db:5432/app'",
    )]})
    found = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={"search": "psql"}).json()["items"]
    assert found
    detail = ep_client.get(f"/endpoint-events/{found[0]['id']}", headers=ep_client.analyst).json()
    assert "Hunter2Password" not in detail["command_line"]
    assert detail["redacted"] is True


def test_event_filters_and_live_polling(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    ep_client.post("/agent/events", headers=cred, json={"events": [
        _event("netw" + "0" * 28, category="network", event_type="network_connection", dst_ip="8.8.8.8", dst_port=53),
    ]})
    net = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={"category": "network"}).json()
    assert all(e["category"] == "network" for e in net["items"]) and net["total"] >= 1
    # after_id for live polling returns only newer rows
    newest = net["items"][0]["id"]
    assert ep_client.get("/endpoint-events", headers=ep_client.analyst, params={"after_id": newest}).json()["total"] == 0
    _err(ep_client.get("/endpoint-events", headers=ep_client.analyst, params={"os_type": "solaris"}), 422, "validation_error")


# --- heartbeats, rotation, revocation ------------------------------------------------
def test_heartbeat_and_health(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    hb = ep_client.post("/agent/heartbeat", headers=cred, json={
        "agent_version": "2.0.0", "os_version": "Windows 11", "hostname": "unit-host",
        "uptime_seconds": 120, "buffer_pending": 3, "send_failures": 0,
        "collectors": [{"name": "windows_security", "status": "permission_denied", "detail": "not admin"}],
    })
    assert hb.status_code == 200 and hb.json()["rotate_credentials"] is False
    devices = ep_client.get("/devices", headers=ep_client.analyst).json()
    dev = next(d for d in devices if d["hostname"] == "unit-host")
    assert dev["connection"] == "online"
    assert any(c["status"] == "permission_denied" for c in dev["collectors"])
    ov = ep_client.get("/endpoint/overview", headers=ep_client.analyst).json()
    assert any(i["collector"] == "windows_security" for i in ov["collector_issues"])


def test_rotation_and_revocation(ep_client, enrolled_device):
    cred, uid, _ = enrolled_device
    dev = next(d for d in ep_client.get("/devices", headers=ep_client.analyst).json() if d["device_uid"] == uid)
    assert ep_client.post(f"/devices/{dev['id']}/rotate", headers=ep_client.admin).status_code == 200
    assert ep_client.post("/agent/heartbeat", headers=cred, json={
        "agent_version": "2.0.0", "os_version": "x", "hostname": "unit-host", "uptime_seconds": 1, "buffer_pending": 0,
    }).json()["rotate_credentials"] is True
    new_cred = ep_client.post("/agent/rotate-credentials", headers=cred).json()["credential"]
    assert new_cred.split(".")[1] != cred["Authorization"].split(".")[1]
    # old credential now rejected
    _err(ep_client.post("/agent/events", headers=cred, json={"events": [_event("z")]}), 401, "invalid_device_credential")

    # revoke (admin only)
    _err(ep_client.post(f"/devices/{dev['id']}/revoke", headers=ep_client.analyst, json={"reason": "test"}), 403, "forbidden")
    assert ep_client.post(f"/devices/{dev['id']}/revoke", headers=ep_client.admin, json={"reason": "compromised"}).status_code == 200
    _err(ep_client.post("/agent/events", headers={"Authorization": f"Bearer {new_cred}"}, json={"events": [_event("z")]}),
         403, "device_revoked")


# --- alert integration ---------------------------------------------------------------
def test_endpoint_alerts_separate_from_access_log(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    ep_client.post("/agent/events", headers=cred, json={"events": [
        _event("ep_alert" + "0" * 24, category="system", event_type="log_cleared", username="admin"),
    ]})
    # endpoint alerts need a token
    _err(ep_client.get("/alerts", params={"source": "endpoint"}), 401, "authentication_required")
    with_token = ep_client.get("/alerts", headers=ep_client.analyst, params={"source": "endpoint"}).json()
    assert with_token["total"] >= 1
    alert = with_token["items"][0]
    assert alert["source"] == "endpoint" and alert["hostname"] == "unit-host"
    detail = ep_client.get(f"/alerts/{alert['id']}", headers=ep_client.analyst).json()
    assert detail["endpoint_event"] is not None
    # resolve works through the shared alert endpoint
    resolved = ep_client.patch(f"/alerts/{alert['id']}", headers=ep_client.analyst,
                              json={"status": "resolved", "resolution_note": "benign admin action", "resolved_by": "Analyst"})
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"


def test_event_time_range_and_sort(ep_client, enrolled_device):
    cred, _, _ = enrolled_device
    base = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    ep_client.post("/agent/events", headers=cred, json={"events": [
        _event(f"range{i}", category="system", event_type="time_probe",
               timestamp=(base + timedelta(minutes=10 * i)).isoformat())
        for i in range(4)  # 12:00, 12:10, 12:20, 12:30 UTC
    ]})
    q = {"search": "time_probe", "start": "2026-03-01T12:05:00Z", "end": "2026-03-01T12:25:00Z"}
    newest = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={**q, "sort": "newest"}).json()
    assert [e["timestamp"] for e in newest["items"]] == ["2026-03-01T12:20:00", "2026-03-01T12:10:00"]
    oldest = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={**q, "sort": "oldest"}).json()
    assert [e["timestamp"] for e in oldest["items"]] == ["2026-03-01T12:10:00", "2026-03-01T12:20:00"]
    # A bound in another timezone (IST, +05:30) means the same instant.
    ist = ep_client.get("/endpoint-events", headers=ep_client.analyst, params={
        "search": "time_probe", "start": "2026-03-01T17:45:00+05:30", "sort": "oldest"}).json()
    assert [e["timestamp"] for e in ist["items"]] == ["2026-03-01T12:20:00", "2026-03-01T12:30:00"]
    _err(ep_client.get("/endpoint-events", headers=ep_client.analyst, params={
        "start": "2026-03-01T12:30:00Z", "end": "2026-03-01T12:00:00Z"}), 422, "validation_error")
