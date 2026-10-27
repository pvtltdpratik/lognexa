"""Shared fixtures: an isolated in-memory SQLite database per test module.

The application code only uses portable SQLAlchemy types, so the API can be
exercised end to end without a PostgreSQL server.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app
from app.services.dataset import reset_and_load
from app.services.pipeline import AnalysisParams, run_analysis
from app.services.synthetic import generate_dataset


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
        reset_and_load(db, generate_dataset(seed=7, n_users=24, days=7, n_records=700))
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
