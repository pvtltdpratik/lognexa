# Implementation Log

Chronological record of the work. Dates are 2026-10-27 unless noted.

## Status summary

| Feature | Status |
|---|---|
| Theme, branding, app shell | ✅ Completed |
| Database models (5 tables) | ✅ Completed |
| Synthetic generator + CSV export + seed script | ✅ Completed |
| Feature engineering, 11 rules, Isolation Forest, scoring, explanations | ✅ Completed |
| Evaluation metrics vs injected labels | ✅ Completed |
| REST API with validation and error envelope | ✅ Completed |
| Dashboard: overview, logs, alerts, risk, analysis pages | ✅ Completed |
| Alert lifecycle (acknowledge / resolve / reopen) | ✅ Completed |
| Backend automated tests (48) | ✅ Completed, passing |
| Lint, type check, production build of the frontend | ✅ Passing |
| End-to-end run on **PostgreSQL** | ⏳ Pending – verified on SQLite only (see "Challenges") |
| Frontend automated (unit/E2E) tests | ⏳ Not implemented – verified manually in the browser |
| Authentication for dashboard users | ❌ Out of scope |

## 1. Repository inspection

Found: Next.js 16.4.3 with React 19.3, Tailwind v4, shadcn/ui `base-sera` style
(Base UI primitives, sharp corners) with all components installed, no theme
configured; Python 3.10 venv in `server/.venv` with FastAPI, SQLAlchemy,
psycopg2-binary, pandas, NumPy, scikit-learn, pytest already installed;
PostgreSQL 18 service running locally; `logo.jpg` (red eye-in-card) at the
repository root. `client/AGENTS.md` warns that this Next.js version has breaking
changes, so the bundled docs in `node_modules/next/dist/docs/` were consulted.

## 2. Theme and branding

- `client/app/globals.css`: replaced the default taupe palette with the
  "Sentinel" OKLCH palette (light + dark), added severity and success tokens and
  `bg-grid` / `tabular` utilities. Kept the shadcn variable names so every
  component picks up the theme.
- `client/app/layout.tsx`: fonts Space Grotesk / IBM Plex Sans / JetBrains Mono,
  `ThemeProvider` (dark default), `TooltipProvider`, `Toaster`, `AppShell`.
- `client/components/brand/logo.tsx`: SVG redraw of the logo.
- Removed the Next.js template SVGs from `client/public`; copied `logo.jpg` there.

## 3. Backend data layer

- `server/app/config.py`: pydantic-settings, env prefix `LOGNEXA_`.
- `server/app/database.py`: engine factory (pool pre-ping for PostgreSQL,
  `StaticPool` for in-memory SQLite), `get_db` dependency, `init_db`.
- `server/app/models.py`: `User`, `AccessLog`, `RiskScore`, `Alert`, `AnalysisRun`.
- `server/app/services/policy.py`: departments, resources, sensitivity and role
  authorisation shared by generator and rules.
- `server/app/services/synthetic.py`, `dataset.py`, `scripts/seed.py`.

## 4. Detection

- `features.py`, `rules.py`, `ml.py`, `scoring.py`, `pipeline.py` (details in
  [ml-methodology.md](ml-methodology.md)).

## 5. API

- `server/app/schemas.py`, `errors.py`, `main.py`, `routers/{logs,alerts,risk,analysis,analytics}.py`.

## 6. Dashboard

- `client/lib/{api,types,schemas,format}.ts`, `client/hooks/use-api.ts`.
- Components: `app-shell`, `severity`, `states`, `pager`, `risk-explanation`,
  `log-detail-sheet`, `alert-action-dialog`.
- Pages: `app/page.tsx`, `app/logs`, `app/alerts`, `app/risk`, `app/analysis`.
- `client/.env.example`, `.env.local`; `.gitignore` now keeps `.env.example`.
- `client/eslint.config.mjs`: ignore shadcn-generated `components/ui/**` and
  `hooks/use-mobile.ts`.
- `.claude/launch.json`: dev-server definitions for `api` and `web`.

## 7. Tests and docs

- `server/tests/` (conftest + 3 test modules), `server/pytest.ini`.
- All Markdown files in `docs/`.

## Design decisions

| Decision | Reason |
|---|---|
| Portable SQLAlchemy types (JSON, String, Float) | Same models on PostgreSQL and SQLite; tests need no DB server |
| JSON columns filtered in Python (`rule_code`, rule-hit counts) | Avoids dialect-specific JSON operators; dataset is small |
| Per-user baselines computed over the window | No separate training period needed; explainable ("for this user") |
| Median-centred ML rescaling | Normal events contribute ~0 instead of a 30–40 point floor |
| Agreement bonus | Rewards independent confirmation by rules and ML |
| Keep acknowledged/resolved alerts on re-analysis | Preserves analyst work and audit history |
| `injected_anomaly` stored but never used as input | Enables honest evaluation without leakage |
| Synchronous `/analyze` | ~1 s for 2,200 events; background jobs unnecessary at this scale |
| Client-side data fetching | Dashboard must show live DB data; avoids server-side fetch caching rules of Cache Components |
| NativeSelect for filters | Accessible, robust on mobile, still a shadcn component |
| Documentation IP ranges and `.test` e-mail domain | Synthetic data can never collide with real hosts or people |

## Challenges and solutions

1. **Global `DATABASE_URL` collision.** The developer machine has a global
   `DATABASE_URL` pointing at an unrelated remote PostgreSQL instance. Because
   environment variables override `.env`, the app tried to load the wrong
   dialect (`postgres://`) and would otherwise have connected to a foreign
   database. *Solution:* all settings use the `LOGNEXA_` prefix
   (`LOGNEXA_DATABASE_URL`).
2. **Relative SQLite path.** Starting uvicorn from the repo root
   (`--app-dir server`) would have created a second, empty DB file. *Solution:*
   relative `sqlite:///` paths are resolved against `server/` in a validator.
3. **Single-rule anomalies scored too low.** With rule points ≤ 45 and w = 0.6,
   2 AM activity scored ≈28 (Medium) and recall at threshold 50 was 3% for
   unusual hours. *Solution:* rescaled rule points (strong indicators 60–75) and
   lowered the default alert threshold to 40 after measuring the
   precision/recall trade-off (table in ml-methodology.md).
4. **React 19 lint rule `set-state-in-effect`.** The first `useApi` hook set
   loading state synchronously in an effect. *Solution:* loading is derived by
   comparing the settled request key with the current one, and the fetcher is
   wrapped in `useEffectEvent`.
5. **`useSearchParams` with Cache Components.** Pages reading `?user=` / `?focus=`
   are wrapped in `<Suspense>` so static prerendering succeeds.
6. **PostgreSQL credentials.** The local PostgreSQL service requires a password
   that was not available during development; the team chose to develop and
   test on SQLite and switch by editing `LOGNEXA_DATABASE_URL`. The schema uses
   only portable types, but a PostgreSQL run is still pending.

---

# v2.0.0 — Cross-platform endpoint monitoring

Upgraded the access-log prototype into a cross-platform endpoint monitoring
system without breaking v1 features or resetting data.

## Status summary (v2)

| Feature | Status |
|---|---|
| Alembic migrations (0001 baseline, 0002 endpoint); v1 auto-adoption | ✅ Completed, tested |
| Endpoint ORM models + schemas (devices, tokens, heartbeats, events; alerts extended) | ✅ Completed |
| Device enrolment, per-device credentials, rotation, revocation | ✅ Completed, tested |
| Dashboard RBAC (analyst/admin bearer tokens) | ✅ Completed, tested |
| Agent API (`/agent/enroll|heartbeat|events|rotate-credentials`) | ✅ Completed, tested |
| Endpoint detection (15 EP rules + Isolation Forest) + correlation | ✅ Completed, tested |
| Server + agent redaction (defence in depth) | ✅ Completed, tested |
| Windows agent + collectors (Security/System/Sysmon/PowerShell/CIM) | ✅ Completed, verified on host |
| Linux agent + collectors (journald/auth.log, /proc, ss, FIM) | ✅ Completed, verified in WSL |
| Durable buffer (persistence, dedup, checkpoints, bounds, retries, backoff) | ✅ Completed, tested |
| Service installers (systemd unit, Windows PowerShell) | ✅ Completed (installers not executed in CI) |
| Dashboard: endpoints, live events, enrolment, event timeline, endpoint alerts | ✅ Completed, verified in browser |
| Tests: 33 backend + 26 agent added | ✅ Completed, passing |
| Docs + README rewrite | ✅ Completed |
| PostgreSQL end-to-end run | ⏳ Pending — verified on SQLite only |
| macOS agent | ❌ Out of scope |

## Files added (v2)

- `server/migrations/` (alembic.ini, env.py, versions 0001/0002), `server/app/migrations.py`, `server/scripts/migrate.py`
- `server/app/security.py`, `server/app/endpoint_schemas.py`
- `server/app/services/{endpoint_detection,endpoint_service,redaction}.py`
- `server/app/routers/{agent,endpoints}.py`
- `server/tests/{test_endpoint_detection,test_endpoint_api,test_migrations}.py`
- `agent/` — full agent package, `deploy/` installers, `tests/`, `pyproject.toml`, config examples
- `client/components/{auth,endpoint-badges,device-detail-sheet,endpoint-event-sheet}.tsx`
- `client/app/{endpoints,events,enrollment}/page.tsx`
- `docs/endpoint-monitoring.md`

## Files modified (v2)

- `server/app/models.py` (endpoint tables; alerts extended), `config.py` (endpoint/auth settings), `database.py` (init via migrations), `main.py` (routers, CORS Authorization), `schemas.py` (alert source), `services/ml.py` (feature param), `routers/{alerts,analytics,risk}.py` + `services/{pipeline,dataset}.py` (scope v1 alert ops to `source='access_log'`)
- `client/lib/{api,types}.ts` (token auth + endpoint types/methods), `app/layout.tsx`, `components/app-shell.tsx` (nav groups, sign-in), `components/states.tsx`, `lib/format.ts`, `app/page.tsx` (endpoint summary), `app/alerts/page.tsx` (endpoint alerts), `next.config.ts` (turbopack root)
- `requirements.txt` (alembic), `.env` examples

## Key design decisions (v2)

| Decision | Reason |
|---|---|
| Alembic with batch mode + programmatic adoption | Migrate without resetting; adopt pre-Alembic v1 DBs; works on SQLite & PostgreSQL |
| One `alerts` table for both sources | Reuses the existing triage workflow and UI; `source` discriminates |
| Agent uses only the standard library | Deployable on locked-down hosts with no pip access; httpx optional |
| Per-device hashed credentials | A DB leak never exposes usable agent credentials |
| Content-hash `event_uid`, unique per device | At-least-once delivery with no duplicate rows; safe retries |
| Two-layer redaction | A stale/misconfigured agent still can't persist secrets |
| Pure-rules fallback when ML unfitted | New/low-volume devices still alert on strong indicators |
| Correlation into incidents | Fewer, richer alerts instead of one per raw event |

## Challenges and solutions (v2)

See the v2 bug table in [testing.md](testing.md): the diluted sparse-data score,
the `wevtutil` single-line XML split, the null-safe basename, the sqlcmd `-P`
redaction, and the Turbopack root resolution were all found by automated tests or
live verification and fixed.

---

# v2.1 — Mock data removed (2026-10-28)

The dashboard now shows only real endpoint telemetry.

- **Database**: backed up to `server/backups/` (git-ignored), then deleted the
  synthetic rows in one transaction: 60 users, 2,200 access logs, 2,200 risk
  scores, 175 access-log alerts, 3 analysis runs. The real enrolled device, its
  1,000 events and 3 endpoint alerts were kept.
- **Backend**: removed `POST /dataset/generate` and its schemas,
  `services/dataset.py`, `scripts/seed.py` and `server/data/*.csv`. The generator
  moved to `server/tests/synthetic.py` as a test fixture. The access-log APIs
  (`/logs`, `/risk-scores`, `/analyze`) remain.
- **Dashboard**: removed `/logs`, `/risk`, `/analysis` and their components. `/`
  is now an endpoint overview; `/alerts` lists endpoint alerts only. Fixed a
  brief "Sign in required" flash on page load (hydration render).
- **Windows installer**: fixed enrolment argument order, UTF-8 BOM in
  `config.json`, and replaced the non-functional service with a SYSTEM startup
  scheduled task; added `install-windows.cmd` and an agent log file.
- **Agent delivery fixes** (found from a live install: 18,906 events stuck,
  93 send failures, every event sharing one timestamp):
  - *Timestamps*: Windows `SystemTime` has 7 fractional digits, which
    `datetime.fromisoformat` rejects on Python 3.10; `_parse_ts` silently fell
    back to the collection time. Extra digits are now trimmed. The CIM process
    collector now uses the real `CreationDate` instead of the scan time.
  - *Stuck queue*: PowerShell script blocks exceed the server's 8,192-char
    `command_line` limit, so the server rejected the whole batch (422) and the
    sender retried that same batch forever. Payloads are now clamped to the
    server schema (`fit_payload`, also applied to already-buffered events), and a
    rejected batch is bisected to isolate bad events into `rejected.jsonl`.
- **Live events filters**: order (newest / oldest / highest risk) and time range
  (last 15 min … 7 days, or a custom From–To in local time). The API now
  normalises timezone-aware `start`/`end` to naive UTC before comparing.
- **Timezone display fix**: the API returns naive UTC, which the dashboard parsed
  as local time, so every time showed 5 h 30 min behind (IST) and enrolment tokens
  looked expired early. `parseApiDate` now treats offset-less values as UTC.
- **Tests**: 81 backend + 33 agent, all passing; lint, type-check and build clean.
