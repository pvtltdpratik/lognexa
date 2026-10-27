# Setup and Deployment

## Prerequisites

| Tool | Version used |
|---|---|
| Python | 3.10 (virtual environment in `server/.venv`) |
| Node.js / npm | Node 20+ |
| PostgreSQL | 18 (any 13+ should work) |
| OS | Developed on Windows 11; commands below use Windows paths |

## 1. Database (PostgreSQL)

Create a dedicated role and database (run once as the `postgres` superuser).
Edit the password in `server/scripts/init_postgres.sql` first:

```bash
psql -U postgres -h localhost -f server/scripts/init_postgres.sql
```

## 2. Backend

```bash
cd server
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `server/.env`:

```ini
LOGNEXA_DATABASE_URL=postgresql+psycopg2://lognexa:<your-password>@localhost:5432/lognexa
LOGNEXA_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
LOGNEXA_RANDOM_SEED=42
```

> Variables are prefixed with `LOGNEXA_` on purpose, so a machine-wide
> `DATABASE_URL` belonging to another project is never used.
>
> Without PostgreSQL you can use `LOGNEXA_DATABASE_URL=sqlite:///./lognexa_dev.db`
> (development only; the path is resolved relative to `server/`).

Create tables, load the synthetic dataset, export CSV samples and run the first
analysis:

```bash
.venv\Scripts\python -m scripts.seed
```

Options: `--seed 7 --users 60 --days 14 --records 2200 --no-analyze`.

Start the API:

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Check: <http://localhost:8000/health> and <http://localhost:8000/docs>.

## 3. Frontend

```bash
cd client
copy .env.example .env.local
npm install
npm run dev
```

`client/.env.local`:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Open <http://localhost:3000>.

Production build:

```bash
npm run build
npm run start
```

## 4. Running tests

```bash
cd server
.venv\Scripts\python -m pytest
```

```bash
cd client
npm run lint
```

## Environment variables

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `LOGNEXA_DATABASE_URL` | server/.env | `postgresql+psycopg2://lognexa:change-me@localhost:5432/lognexa` | SQLAlchemy URL |
| `LOGNEXA_CORS_ORIGINS` | server/.env | `http://localhost:3000,http://127.0.0.1:3000` | Allowed browser origins |
| `LOGNEXA_RANDOM_SEED` | server/.env | `42` | Seed for the forest (and seed-script default) |
| `NEXT_PUBLIC_API_URL` | client/.env.local | `http://localhost:8000` | Backend URL used by the browser |

`.env` and `.env.local` are git-ignored; only the `.env.example` templates are
committed. No real credentials are stored in the repository.

## Sample data

`server/data/sample_users.csv` and `server/data/sample_access_logs.csv` are
exported by the seed script (seed 42) for inspection in a spreadsheet. They
include the `injected_anomaly` ground-truth column.

## Deployment notes (not performed)

The project was only run locally. For a hosted demo:

- Run the API with `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`
  behind a reverse proxy with HTTPS.
- Use a managed PostgreSQL instance and set `LOGNEXA_DATABASE_URL` as a secret.
- Set `LOGNEXA_CORS_ORIGINS` to the deployed frontend origin.
- Build the frontend with `NEXT_PUBLIC_API_URL` pointing at the public API.
- Add authentication before exposing it: the API currently has none, and
  `POST /dataset/generate` deletes all data.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows "Backend unavailable" | Start the API on port 8000, check `NEXT_PUBLIC_API_URL`, then press Retry |
| `/health` returns `degraded` / API returns `database_error` | Check `LOGNEXA_DATABASE_URL`, that PostgreSQL is running and the password is right |
| CORS error in browser console | Add the frontend origin to `LOGNEXA_CORS_ORIGINS` and restart the API |
| Empty dashboard | Run `python -m scripts.seed` or use *Regenerate dataset* on the Analysis page |
