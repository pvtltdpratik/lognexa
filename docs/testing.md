# Testing

## How to run

```bash
cd server
.venv\Scripts\python -m pytest            # 48 tests, ~5 s
```

```bash
cd client
npx tsc --noEmit      # type check
npm run lint          # ESLint (next/core-web-vitals + typescript)
npm run build         # production build
```

Tests use an in-memory SQLite database (`tests/conftest.py`), seeded with a
small synthetic dataset (seed 7, 24 users, 7 days, 700 events) and analysed once
per module. No PostgreSQL server is needed.

## Latest results (2026-10-27)

| Check | Result |
|---|---|
| `pytest` | **48 passed** in 5.3 s |
| `tsc --noEmit` | 0 errors |
| `eslint .` | 0 errors, 0 warnings |
| `next build` | Success; `/`, `/logs`, `/alerts`, `/risk`, `/analysis` prerendered |

## Automated test cases

### `test_synthetic.py` – generator (7 tests)

| Test | Verifies |
|---|---|
| default dataset shape | 60 users, 2,200 logs, 14 distinct days |
| all four anomaly types | each label present with ≥ 20 events |
| same seed reproducible | identical users and logs for the same seed |
| different seed | data changes |
| sorted / valid users | logs time-ordered, every `user_id` exists |
| sensitive-access labels | every injected event violates the role policy |
| reserved IP ranges | only 10/8, 192.0.2/24, 198.51.100/24, 203.0.113/24 |

### `test_detection.py` – features, rules, scoring (20 tests)

| Test | Verifies |
|---|---|
| severity bands (8 parametrised) | exact boundaries 25 / 50 / 75 |
| combine formula | weights, agreement bonus only when a rule fired, clipping at 100 |
| bad weight | `rule_weight > 1` raises |
| failed-login window | rolling count 1…6 and R1A fires |
| outside window | failures 90 min apart are not accumulated |
| unauthorised restricted access | R4A fires, score ≥ 75 |
| authorised role | no sensitive-access rule for an authorised analyst |
| normal event | no rules, score 0 |
| missing columns | `ValueError` |
| scores within bounds | risk and ML in 0–100, valid severities |
| anomalies vs normal | mean risk of injected events > 3 × normal |
| useful but not perfect | recall ≥ 0.8, precision ≥ 0.6, and at least one FP or FN exists |
| explanations | every event has an explanation |

### `test_api.py` – endpoints (21 tests)

| Area | Cases |
|---|---|
| Health / overview | DB ok, counts equal seeded data, 24 hourly buckets, latest run completed |
| Logs | pagination maths, status and severity filters, risk sort order, search, invalid `page_size`/`page`/enum/date, reversed date range, detail with explanation, 404 |
| Risk scores | `min_score` filter, `min > max` rejected, malformed `rule_code` rejected, rule-code filter, methodology, user ranking order |
| Alerts | list + detail consistency; resolve without note / analyst / bad status / extra field → 422; full lifecycle acknowledge → duplicate (409) → resolve → reopen; 404 |
| Analysis | invalid contamination / weight / unknown field → 422; re-analysis keeps resolved alerts and returns metrics; dataset generation validation |
| Empty DB | empty pagination, overview zeros, `/analyze` → 409 `no_data`, `/analyze/latest` → 404, generating data on an empty DB |

## Manual end-to-end verification (browser)

Performed against the running stack (FastAPI on :8000 with the seeded SQLite DB,
Next.js dev server on :3000):

| # | Scenario | Result |
|---|---|---|
| 1 | Overview loads real counts (2,200 events, 175 alerts, P/R/F1 0.78/0.96/0.86) | ✅ |
| 2 | Alerts → Resolve with empty form shows both inline errors | ✅ |
| 3 | Resolve with valid name and note → success toast, dialog closes, alert leaves Open tab, status persisted in API | ✅ |
| 4 | Logs `?user=11` pre-filters (29 events, 2 pages) | ✅ |
| 5 | End date before start date → inline error, request not sent | ✅ |
| 6 | Row click opens detail sheet with rules, scores and formula | ✅ |
| 7 | Analysis form: contamination 0.5 → "Maximum is 0.2", submit disabled | ✅ |
| 8 | Run analysis → loading label, toast "174 new alerts", run history updated (resolved alert kept) | ✅ |
| 9 | Risk page: methodology, 31 table rows, no horizontal overflow | ✅ |
| 10 | 375 px mobile viewport on /logs and /: no page-level horizontal scroll | ✅ |
| 11 | API stopped → "Backend unavailable" + Retry; after API start, Retry restores data | ✅ |

## Bugs found and fixed

| Bug | Cause | Fix |
|---|---|---|
| Settings loaded a foreign `postgres://` URL | Global `DATABASE_URL` env var overrides `.env` | `LOGNEXA_` env prefix |
| Single-rule anomalies under-scored | Rule points too small relative to weight | Rescaled points, threshold 40 |
| `TS2322: unknown is not assignable to ReactNode` | `{error && <ErrorState/>}` with `error: unknown` | `{!!error && …}` |
| ESLint `set-state-in-effect`, non-literal deps | Original `useApi` design | Derived loading state + `useEffectEvent` |
| Risk explanation always showed w = 0.6 | Weight not stored with the score | `rule_weight` saved in `features` |

## Known gaps

- No frontend unit or Playwright tests; UI flows were checked manually.
- Tests run on SQLite only; PostgreSQL-specific behaviour (e.g. JSON type,
  connection errors) is untested.

---

## v2 endpoint-monitoring tests

### Backend (total now 81; 33 added for v2)

| Module | Tests | Covers |
|---|---|---|
| `test_endpoint_detection.py` | 17 | Command indicators; Windows & Linux rules (brute force, suspicious commands, persistence, sensitive files, log clearing, rare external connections); score bounds; sparse-data pure-rule fallback; explanations |
| `test_endpoint_api.py` | 13 | Auth required & role enforcement; `503` when tokens unconfigured; enrolment flow & token limits; bad-input rejection; device auth; ingest + **dedup** + detection; batch limits; **redaction on ingest**; event filters & live polling; heartbeat/health; **rotation & revocation**; endpoint alerts separate from access-log alerts |
| `test_migrations.py` | 3 | Fresh upgrade to full schema (idempotent); **pre-Alembic v1 adoption without data loss**; partial-schema refused |

### Agent (`agent/tests`, 26 tests)

| Module | Tests | Covers |
|---|---|---|
| `test_buffer.py` | 7 | Add/peek/ack; dedup on uid; **persistence across reopen**; FIFO order; **bounded size drops oldest**; safe ack of unknown |
| `test_redaction.py` | 11 | Passwords, DB flags (mysql `-p`, sqlcmd `-P`), connection strings, API keys, bearer tokens, `net user`, private-key blocks; benign text unchanged; redact-by-key; in-place event redaction |
| `test_models_and_collectors.py` | 8 | Event uid stability & device scoping; payload shape; collector availability reasons; **the other platform's collectors report `unsupported`**; broken collector never raises; checkpoint persistence; HTTPS enforcement |

### Latest results

| Check | Result |
|---|---|
| `server` pytest | **81 passed** (v2.1: dataset-API tests replaced by a removal check; + event time-range/sort) |
| `agent` pytest | **33 passed** (v2.1: + BOM-tolerant config, log file, timestamp precision, schema fitting, poison-event isolation) |
| `tsc --noEmit` | 0 errors |
| `eslint .` | 0 errors, 0 warnings |
| `next build` | Success; 6 routes prerendered (v2.1: access-log pages removed) |

### Live end-to-end verification

- Full agent↔API flow (enrol → send → detect → correlate → alert → resolve;
  rotation; revocation; dedup; redaction) — 28 assertions, all pass.
- Windows collectors on this host: Security, System, Sysmon, PowerShell and
  process collectors all returned real events.
- Linux collectors in Ubuntu WSL: journald auth, `/proc`, `ss` all returned real events.
- Dashboard: endpoint inventory, device detail (collector health), live events,
  event detail with timeline, endpoint alerts with correlation, RBAC gating —
  all verified in the browser.

### Bugs found and fixed (v2)

| Bug | Cause | Fix |
|---|---|---|
| Endpoint rules never alerted with few events | `risk = 0.6 × rule` diluted scores below threshold when ML unfitted | Sparse-data path uses pure rule score |
| `sqlcmd -P` password not redacted | Flag not in redaction list | Added sqlcmd/osql `-P` pattern (agent + server) |
| Windows event-log collectors returned 0 events | `wevtutil /f:xml` emits all records on one line; line-based split produced one unparseable blob | Split on `<Event>…</Event>` with a regex |
| Security collector crashed | `os.path.basename(None)` on empty XML elements | Null-safe `_base()` helper |
| Dashboard CSS failed to load (dev) | Turbopack root inferred from an unrelated lockfile | Pinned `turbopack.root` in `next.config.ts` |
