"""Lognexa FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000   (from the server/ folder)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.errors import register_error_handlers
from app.routers import agent, alerts, analysis, analytics, endpoints, logs, risk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception:  # keep the API up so /health can report the problem
        logging.getLogger("lognexa").exception("database initialisation failed")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "AI-driven access-log auditing and cross-platform endpoint monitoring "
        "(student prototype). Agent endpoints live under /agent; endpoint telemetry APIs "
        "require an analyst or admin bearer token."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
register_error_handlers(app)

for r in (analytics.router, logs.router, alerts.router, risk.router, analysis.router, endpoints.router, agent.router):
    app.include_router(r)


@app.get("/", include_in_schema=False)
def root():
    return {"name": settings.app_name, "version": settings.version, "docs": "/docs"}
