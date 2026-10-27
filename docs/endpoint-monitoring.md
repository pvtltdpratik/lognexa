# Endpoint Monitoring (v2)

Cross-platform endpoint security monitoring for Windows and Linux, built on top
of the v1 access-log auditing engine. Agents collect OS telemetry, ship it
securely to the FastAPI backend, which scores it with the same hybrid
(rules + Isolation Forest) engine and correlates related events into incidents.

## Components

| Component | Location | Role |
|---|---|---|
| Agent | `agent/lognexa_agent/` | Collect, buffer, redact and ship telemetry; heartbeats |
| Collectors | `agent/lognexa_agent/collectors/` | OS-native data sources (Windows / Linux) |
| Durable buffer | `agent/lognexa_agent/buffer.py` | SQLite buffer: persistence, dedup, checkpoints, bounds |
| Agent API | `server/app/routers/agent.py` | `/agent/enroll`, `/heartbeat`, `/events`, `/rotate-credentials` |
| Dashboard API | `server/app/routers/endpoints.py` | Devices, events, overview, enrolment tokens |
| Device auth | `server/app/security.py` | Per-device credentials, dashboard RBAC, transport checks |
| Detection | `server/app/services/endpoint_detection.py` | Features + `EP-*` rules + Isolation Forest |
| Ingest/correlation | `server/app/services/endpoint_service.py` | Dedup, scoring, alert correlation |
| Redaction | `server/app/services/redaction.py` + agent copy | Strip secrets before storage |

## Enrolment and credentials

```mermaid
sequenceDiagram
    participant A as Admin (dashboard)
    participant S as Server
    participant G as Agent
    A->>S: POST /enrollment-tokens (admin)
    S-->>A: plaintext token (shown once; only its hash stored)
    A->>G: provide token (env / installer)
    G->>S: POST /agent/enroll {token, hostname, os, machine_id}
    S-->>G: device_uid + credential (device_uid.secret)
    Note over S: stores SHA-256(secret) only
    G->>S: POST /agent/events  (Bearer device_uid.secret, HTTPS)
    G->>S: POST /agent/heartbeat (health, buffer depth, collectors)
    S-->>G: {rotate_credentials: true?}
    G->>S: POST /agent/rotate-credentials (if asked)
```

- **Enrolment tokens**: limited-use, time-limited, admin-created. Re-enrolling the
  same `machine_id` reuses the device row and replaces its credential, keeping history.
- **Device credential**: `<device_uid>.<secret>`; only `SHA-256(secret)` is stored.
- **Rotation**: admin requests it; the agent rotates on its next heartbeat.
- **Revocation**: admin revokes; the credential stops working immediately
  (`403 device_revoked`); telemetry is retained.

## Reliable collection

| Guarantee | Implementation |
|---|---|
| Persistence | Events committed to a local SQLite WAL buffer before sending |
| Retries / backoff | Sender loop retries with exponential backoff (to 5 min) on 5xx / network errors |
| Checkpoint recovery | Events are deleted only after the server acknowledges them |
| Deduplication | `event_uid` (content/record hash) is the buffer PK **and** unique per device server-side → at-least-once delivery, no duplicate rows |
| Bounded size | Oldest events dropped past `max_buffer_events`; drop count reported in heartbeats |
| Auto-start | systemd unit (Linux) and Windows service with automatic restart |
| Health | Heartbeats report uptime, buffer depth, send failures, privilege and per-collector status |

Agent threads: **collector** (poll → redact → buffer), **sender** (drain → ack),
**heartbeat**. A broken collector is caught and reported; it never stops the agent.

## Collectors

See the capability table in the [README](../README.md#-monitoring-capabilities).
Each collector's `available()` returns `ok` / `unsupported` / `permission_denied`
/ `error` with a reason, surfaced on the Endpoints page and in `collectors` /
`test-collectors` CLI output. Windows event logs are read via `wevtutil` XML
queries (checkpointed by `EventRecordID`); Linux auth via journald (cursor) or
`/var/log/auth.log` (byte offset); processes via `/proc` or CIM; network via `ss`
socket diffing; file integrity via content hashing.

## Detection and correlation

Features are computed per device over a look-back window (hour-of-day deviation,
failed-logon counts, process/destination rarity, external-destination flag,
command-line length and indicator count, category one-hots). The 15 `EP-*` rules
add points with human-readable reasons; an Isolation Forest adds an anomaly score
when the device has ≥ 50 events (otherwise pure rules are used). Risk and severity
use the same formula and bands as the access-log engine.

**Correlation**: when a new high-risk event would raise an alert, Lognexa looks
for an open endpoint incident on the same host with the same correlation key
(user / IP / host) within `correlation_window_minutes` (default 30). If found, the
event is added to that incident (bumping its `event_count`, severity and risk);
otherwise a new alert is created. The event-detail view also shows an
**investigation timeline** of events linked by shared user, IP or process tree
within ±15 minutes.

## Security

- HTTPS required for agent traffic (loopback exempt); optional trusted-proxy headers.
- Per-device hashed credentials; rotation and revocation.
- Dashboard RBAC: `analyst` (read) < `admin` (tokens, rotate, revoke). Endpoint
  data is never served without a valid token (access-log endpoints stay open for v1).
- Constant-time credential/token comparison; uniform error messages so tokens
  and devices can't be probed.
- Two-layer redaction (agent + server).
- No automated destructive response.

## Platform limitations (documented, not hidden)

- Windows Security log and 4688 command-line auditing need Administrator / policy; without it the agent reports `permission_denied` and relies on Sysmon/CIM.
- Sysmon is optional; if absent, that collector reports `unsupported`.
- Linux journald access needs the `systemd-journal` group; without a journal the agent falls back to `/var/log/auth.log`.
- `/proc` polling catches processes alive at poll time; very short-lived processes may be missed (auditd/Sysmon close this gap).
- No macOS agent in this version.
