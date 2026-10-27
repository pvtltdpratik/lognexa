# API Reference

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs` (Swagger UI)
and `/redoc`. All responses are JSON.

## Error envelope

Every error uses the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      { "field": "page_size", "location": "query", "message": "Input should be less than or equal to 100", "type": "less_than_equal" }
    ]
  }
}
```

| HTTP | code | When |
|---|---|---|
| 422 | `validation_error` | Invalid query/path/body value, missing field, unknown body field, bad date range |
| 404 | `not_found` | Log / alert / run does not exist, unknown route |
| 409 | `no_change` | Alert already in the requested status |
| 409 | `no_data` | `/analyze` called with an empty database |
| 422 | `analysis_failed` / `invalid_dataset_parameters` | Pipeline or generator rejected the input |
| 503 | `database_error` | Database unreachable or query failed (details only in server log) |
| 500 | `internal_error` | Unexpected error |

## Pagination

List endpoints return:

```json
{ "items": [...], "total": 2200, "page": 1, "page_size": 25, "pages": 88 }
```

`page` ≥ 1 (≤ 10,000), `page_size` 1–100.

---

## `GET /health`

Service and database status. Never raises; reports `degraded` if the DB fails.

```json
{
  "status": "ok", "database": "ok", "database_backend": "postgresql", "version": "1.0.0",
  "counts": { "users": 60, "logs": 2200, "risk_scores": 2200, "alerts": 175 },
  "detail": null
}
```

## `GET /logs`

| Param | Type / validation | Description |
|---|---|---|
| page, page_size | int, see pagination | |
| search | string 1–100 | Case-insensitive match on username, IP, resource, city |
| user_id | int ≥ 1 | |
| action | `login`\|`logout`\|`file_read`\|`file_write`\|`download`\|`admin_action` | |
| status | `success`\|`failure`\|`denied` | |
| sensitivity | `public`\|`internal`\|`confidential`\|`restricted` | |
| severity | `low`\|`medium`\|`high`\|`critical` | From the latest risk score |
| min_risk | float 0–100 | |
| has_alert | bool | |
| start, end | ISO-8601 datetime | `end` must not be earlier than `start` |
| sort | `timestamp_desc` (default)\|`timestamp_asc`\|`risk_desc` | |

Example: `GET /logs?severity=critical&sort=risk_desc&page_size=2`

```json
{
  "items": [{
    "id": 1986, "user_id": 11, "username": "nverma", "timestamp": "2026-10-13T19:43:07",
    "ip_address": "203.0.113.129", "country": "US", "city": "Ashburn",
    "device": "Kali Linux / Firefox", "action": "login", "resource": "/auth/sso",
    "resource_sensitivity": "public", "status": "success",
    "risk_score": 100.0, "severity": "critical", "has_alert": true
  }],
  "total": 84, "page": 1, "page_size": 2, "pages": 42
}
```

## `GET /logs/{log_id}`

Log plus `user`, full `risk` object (see below), `alert` summary and the
synthetic `injected_anomaly` label. `404` if missing.

Risk object:

```json
{
  "rule_score": 100.0, "ml_score": 93.1, "ml_is_anomaly": true, "risk_score": 100.0, "severity": "critical",
  "triggered_rules": [
    { "code": "R1B", "name": "Repeated failed logins", "category": "failed_logins", "points": 40,
      "reason": "4 failed logins for this account within 60 minutes" }
  ],
  "features": { "hour_deviation": 6.1, "failed_logins_1h": 4, "ip_user_share": 0.1379, "rule_weight": 0.6 },
  "top_features": [{ "feature": "failed_logins_1h", "label": "Failed logins by this user in the previous 60 minutes", "value": 4, "z_score": 9.8 }],
  "explanation": "Rules triggered: ... Isolation Forest marked this event as an outlier (ML score 93/100). ..."
}
```

## `GET /alerts`

| Param | Validation |
|---|---|
| page, page_size | page_size default 20 |
| status | `open`\|`acknowledged`\|`resolved` |
| severity | severity enum |
| user_id | int ≥ 1 |
| search | string 1–100 (username, title, resource, IP) |
| sort | `risk_desc` (default)\|`newest`\|`oldest` |

## `GET /alerts/{alert_id}`

Alert with the underlying `log` and `risk` objects.

## `PATCH /alerts/{alert_id}`

Change alert status. Unknown fields are rejected.

| Field | Rule |
|---|---|
| status | required: `open`, `acknowledged` or `resolved` |
| resolution_note | ≤ 500 chars; **required, ≥ 10 chars** when `status = resolved` |
| resolved_by | ≤ 80 chars; **required, ≥ 2 chars** when `status = resolved` |

```http
PATCH /alerts/161
Content-Type: application/json

{ "status": "resolved", "resolved_by": "A. Analyst", "resolution_note": "Confirmed brute-force from test range; password reset." }
```

Responses: `200` updated alert, `404`, `409 no_change` (e.g. acknowledging an
already-acknowledged alert), `422` validation. Reopening clears
`resolved_by`/`resolved_at`.

## `GET /risk-scores`

| Param | Validation |
|---|---|
| page, page_size | |
| severity | severity enum |
| min_score, max_score | 0–100, `min_score ≤ max_score` |
| user_id | int ≥ 1 |
| rule_code | pattern `^R[0-9][A-Z]$` (e.g. `R4A`) |
| sort | `risk_desc` (default)\|`risk_asc`\|`newest` |

Items: `{id, log_id, user_id, username, timestamp, action, resource, rule_score, ml_score, risk_score, severity, rule_codes}`.

## `GET /risk-scores/users?limit=10`

Per-user aggregates (`limit` 1–500): events, avg_risk, max_risk,
high_risk_events (risk ≥ 50), open_alerts; ordered by max then average risk.

## `GET /risk-scores/methodology`

The formula, default weight, agreement bonus, severity bands and every rule with
its points, served from the same constants the pipeline uses.

## `GET /risk-scores/log/{log_id}`

Risk object for one log; `404` if not analysed.

## `POST /analyze`

Re-runs the full pipeline. Body is optional (defaults shown); unknown fields rejected.

```json
{ "contamination": 0.05, "alert_threshold": 40, "rule_weight": 0.6 }
```

| Field | Validation |
|---|---|
| contamination | 0.01 – 0.2 |
| alert_threshold | 1 – 100 |
| rule_weight | 0 – 1 |

Returns the `analysis_runs` row:

```json
{
  "id": 2, "status": "completed", "logs_analyzed": 2200, "alerts_created": 174,
  "parameters": { "contamination": 0.05, "alert_threshold": 40.0, "rule_weight": 0.6, "seed": 42 },
  "metrics": {
    "combined": { "tp": 137, "fp": 38, "fn": 6, "tn": 2019, "precision": 0.783, "recall": 0.958, "f1": 0.862 },
    "caveat": "Measured against labels injected by the synthetic generator; not an estimate of real-world accuracy."
  }
}
```

`409 no_data` if there are no logs.

## `GET /analyze/runs?limit=10` · `GET /analyze/latest`

Run history (newest first) and the most recent run (`404` if none).

## ~~`POST /dataset/generate`~~ (removed in v2.1)

The synthetic-data generator was removed from the application; the app stores
only real data. The endpoint now returns `404`. The generator survives only as a
test fixture (`server/tests/synthetic.py`).

## `GET /analytics/overview`

Everything the dashboard overview needs: totals, alert status counts, severity
counts (all events and unresolved alerts), rule-hit frequencies, daily series
(events, failed, alerts, avg_risk), 24-hour histogram, top 8 users, latest run,
and the period start/end.

## `GET /users`

All users ordered by username (used for the log filter dropdown).
