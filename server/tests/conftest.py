"""Shared fixtures: an isolated in-memory SQLite database per test module.

The application code only uses portable SQLAlchemy types, so the API can be
exercised end to end without a PostgreSQL server.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app
from app.services.pipeline import AnalysisParams, run_analysis
from tests.synthetic import generate_dataset, load_dataset


@pytest.fixture(scope="module")
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture(scope="module")
def seeded(session_factory):
    """Small dataset (fast) loaded and analysed once per module."""
    with session_factory() as db:
        load_dataset(db, generate_dataset(seed=7, n_users=24, days=7, n_records=700))
        run_analysis(db, AnalysisParams(seed=7))
    return session_factory


@pytest.fixture(scope="module")
def client(seeded):
    def _get_db():
        db = seeded()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def empty_client(session_factory):
    """Client bound to a fresh, empty database."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


# --- endpoint monitoring fixtures ---------------------------------------------
ADMIN_TOKEN = "test-admin-token"
ANALYST_TOKEN = "test-analyst-token"


@pytest.fixture(scope="module")
def endpoint_env():
    """Configure auth tokens by refreshing the cached Settings (env + cache clear)."""
    import os

    from app.config import get_settings

    os.environ["LOGNEXA_ADMIN_TOKEN"] = ADMIN_TOKEN
    os.environ["LOGNEXA_ANALYST_TOKEN"] = ANALYST_TOKEN
    os.environ["LOGNEXA_AGENT_REQUIRE_HTTPS"] = "false"  # TestClient is plain http loopback
    get_settings.cache_clear()
    yield get_settings()
    for key in ("LOGNEXA_ADMIN_TOKEN", "LOGNEXA_ANALYST_TOKEN", "LOGNEXA_AGENT_REQUIRE_HTTPS"):
        os.environ.pop(key, None)
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def ep_client(session_factory, endpoint_env):
    """Client on a dedicated DB with auth configured, plus header helpers."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        c.admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        c.analyst = {"Authorization": f"Bearer {ANALYST_TOKEN}"}
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def enrolled_device(ep_client):
    """Create a token, enrol a Windows device, return (headers, device_uid, info)."""
    r = ep_client.post("/enrollment-tokens", headers=ep_client.admin,
                       json={"label": "test", "max_uses": 10, "expires_in_hours": 1})
    token = r.json()["token"]
    enr = ep_client.post("/agent/enroll", json={
        "token": token, "hostname": "unit-host", "os_type": "windows",
        "os_version": "Windows 11", "agent_version": "2.0.0", "machine_id": "UNIT-MACHINE-1",
    }).json()
    cred = {"Authorization": f"Bearer {enr['credential']}"}
    return cred, enr["device_uid"], enr
