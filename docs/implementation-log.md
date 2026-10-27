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
