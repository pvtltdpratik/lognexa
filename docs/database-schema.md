# Database Schema

Defined in `server/app/models.py` (SQLAlchemy 2 declarative models). Tables are
created automatically on API start-up and by `scripts/seed.py`
(`Base.metadata.create_all`). Only portable column types are used, so the same
schema runs on PostgreSQL (target) and SQLite (tests / local fallback). JSON
columns map to `json` on PostgreSQL.

## Entity-relationship diagram

```mermaid
erDiagram
    users ||--o{ access_logs : "performs"
    access_logs ||--o| risk_scores : "scored as"
    access_logs ||--o| alerts : "may raise"
    users ||--o{ alerts : "subject of"
    analysis_runs ||--o{ risk_scores : "produced"
    analysis_runs |o--o{ alerts : "created by"

    users {
        int id PK
        varchar username UK
        varchar full_name
        varchar email UK
        varchar department
        varchar role
        char2 home_country
        varchar home_city
        varchar shift
        timestamp created_at
    }
    access_logs {
        int id PK
        int user_id FK
        timestamp timestamp
        varchar ip_address
        char2 country
        varchar city
        varchar device
        varchar action
        varchar resource
        varchar resource_sensitivity
        varchar status
        varchar injected_anomaly "nullable, evaluation only"
    }
    risk_scores {
        int id PK
        int log_id FK,UK
        int run_id FK
        float rule_score
        float ml_score
        bool ml_is_anomaly
        float risk_score
        varchar severity
        json triggered_rules
        json features
        json top_features
        text explanation
        timestamp created_at
    }
    alerts {
        int id PK
        int log_id FK,UK
        int user_id FK
        int run_id FK "nullable"
        varchar severity
        float risk_score
        varchar title
        text description
        varchar status
        text resolution_note
        varchar resolved_by
        timestamp resolved_at
        timestamp created_at
        timestamp updated_at
    }
    analysis_runs {
        int id PK
        timestamp started_at
        timestamp completed_at
        varchar status
        int logs_analyzed
        int alerts_created
        json parameters
        json metrics
        text error
    }
```

## Tables

### `users`
Synthetic employees (60 by default).

| Column | Type | Notes |
|---|---|---|
| id | integer PK | |
| username | varchar(64) unique, indexed | e.g. `nverma` |
| full_name | varchar(120) | |
| email | varchar(160) unique | `@lognexa-demo.test` (reserved test domain) |
| department | varchar(64) indexed | Engineering, Finance, Human Resources, Sales, Operations, IT Security |
| role | varchar(64) | developer, financial_analyst, hr_specialist, sales_executive, sysops, it_admin |
| home_country / home_city | varchar | All users are based in India (IN) |
| shift | varchar(16) | `day` or `night` (a third of Operations staff) |
| created_at | timestamp | server default `now()` |

### `access_logs`
One row per access event (2,200 by default).

| Column | Type | Notes |
|---|---|---|
| id | integer PK | |
| user_id | FK → users.id, `ON DELETE CASCADE`, indexed | |
| timestamp | timestamp, indexed | Naive timestamps in local office time |
| ip_address | varchar(45) | Only RFC 1918 / RFC 5737 documentation ranges |
| country, city | varchar | Generated, not geo-resolved |
| device | varchar(64) | e.g. `Windows 11 / Chrome`, `Linux / curl` |
| action | varchar(32), indexed | login, logout, file_read, file_write, download, admin_action |
| resource | varchar(160) | e.g. `/finance/payroll`, `/auth/sso` |
| resource_sensitivity | varchar(16), indexed | public, internal, confidential, restricted |
| status | varchar(16), indexed | success, failure, denied |
| injected_anomaly | varchar(32), nullable | Ground-truth label from the generator. **Never used as a detection input**; only for evaluation |

Composite index `ix_access_logs_user_ts (user_id, timestamp)` supports per-user
time-ordered queries.

### `risk_scores`
One row per log for the latest analysis run (replaced on each run).

| Column | Type | Notes |
|---|---|---|
| log_id | FK → access_logs.id, unique | 1 : 1 with a log |
| run_id | FK → analysis_runs.id | |
| rule_score | float 0–100 | Sum of rule points, capped |
| ml_score | float 0–100 | Rescaled Isolation Forest score |
| ml_is_anomaly | boolean | Forest prediction == −1 |
| risk_score | float 0–100, indexed | Combined score |
| severity | varchar(16), indexed | low / medium / high / critical |
| triggered_rules | JSON list | `[{code, name, category, points, reason}]` |
| features | JSON object | Feature values used (plus `rule_weight` of the run) |
| top_features | JSON list | `[{feature, label, value, z_score}]` – explainability heuristic |
| explanation | text | Human-readable summary |

### `alerts`
Raised for events with `risk_score ≥ alert_threshold` (default 40).

| Column | Type | Notes |
|---|---|---|
| log_id | FK → access_logs.id, unique | At most one alert per event |
| user_id | FK → users.id | Denormalised for fast per-user queries |
| run_id | FK → analysis_runs.id, `SET NULL` | Run that created it |
| severity, risk_score | snapshot at creation | |
| title, description | text | Derived from the highest-weighted rule category |
| status | varchar(16), indexed | open, acknowledged, resolved |
| resolution_note, resolved_by, resolved_at | nullable | Required when resolving (validated by the API) |
| created_at, updated_at | timestamp | |

### `analysis_runs`
Audit trail of every analysis.

| Column | Type | Notes |
|---|---|---|
| status | varchar(16) | running, completed, failed |
| parameters | JSON | contamination, alert_threshold, rule_weight, seed |
| metrics | JSON | precision/recall/F1 (combined, rules-only, ML-only), per-type recall, caveat |
| error | text | Populated when a run fails |

## Re-analysis semantics

- `risk_scores` are fully replaced.
- Alerts with status `open` are deleted and regenerated; `acknowledged` and
  `resolved` alerts are **kept**, so analyst work survives a re-run.
- `POST /dataset/generate` deletes all tables' rows (demo data only) before
  loading a new dataset.

## PostgreSQL setup

See `server/scripts/init_postgres.sql` and
[setup-and-deployment.md](setup-and-deployment.md).

---

## v2 endpoint-monitoring tables

Added by Alembic migration `0002` (see [endpoint-monitoring.md](endpoint-monitoring.md)).
Migration `0001` is the v1 baseline; a pre-Alembic v1 database is adopted
(stamped at `0001`) and upgraded without data loss.

### `enrollment_tokens`
Limited-use enrolment secrets. Only `token_hash` (SHA-256) and a short
`token_prefix` are stored; the plaintext is shown once. Columns: `label`,
`max_uses`, `uses`, `revoked`, `expires_at`.

### `devices`
An enrolled endpoint. Key columns: `device_uid` (unique), `hostname`, `os_type`
(windows/linux), `os_version`, `agent_version`, `machine_id`, `ip_address`,
`status` (active/revoked), `credential_hash` (SHA-256 of the device secret),
`credential_issued_at`, `rotation_requested`, `last_seen_at`, `health` (JSON:
latest heartbeat), `revoked_at`, `revoked_reason`, `enrollment_token_id`.

### `device_heartbeats`
Rolling health snapshots per device (`received_at`, `payload` JSON). Pruned to the
most recent N per device.

### `endpoint_events`
Normalised telemetry. `(device_id, event_uid)` is unique → server-side
deduplication. Collected fields: `timestamp`, `os_type`, `source`, `category`,
`event_type`, `username`, `process_name/path`, `command_line`, `pid`,
`parent_process/pid`, `src_ip`, `dst_ip`, `dst_port`, `file_path`, `message`,
`raw` (JSON), `redacted`. Detection fields (null until scored): `rule_score`,
`ml_score`, `ml_is_anomaly`, `risk_score`, `severity`, `triggered_rules` (JSON),
`explanation`, `scored_at`.

### `alerts` (extended)
`source` ('access_log' | 'endpoint'; existing rows default to 'access_log');
`log_id` / `user_id` made nullable; added `device_id`, `endpoint_event_id`
(unique), `correlation_key`, `event_count`, `related_event_ids` (JSON). An
endpoint alert aggregates correlated events into one incident.

```mermaid
erDiagram
    enrollment_tokens ||--o{ devices : "enrols"
    devices ||--o{ device_heartbeats : "reports"
    devices ||--o{ endpoint_events : "collects"
    devices ||--o{ alerts : "endpoint alerts"
    endpoint_events ||--o| alerts : "primary event"
```
