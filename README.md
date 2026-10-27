# Lognexa

AI-driven access-log auditing and anomaly detection — a final-year B.E./B.Tech
CSE student prototype. Rules + Isolation Forest → explainable risk scores,
severity levels and alerts, shown in a Next.js dashboard backed by FastAPI and
PostgreSQL.

> All data is 100% synthetic. This is not production security software.

## Run it

```bash
cd server
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m scripts.seed
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd client
copy .env.example .env.local
npm install
npm run dev
```

Dashboard: <http://localhost:3000> · API docs: <http://localhost:8000/docs>

Full documentation lives in [docs/](docs/README.md).
