"""Migrations must upgrade cleanly and adopt a pre-Alembic v1 database safely."""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.database import make_engine
from app.migrations import upgrade_database

ALL_TABLES = {
    "users", "access_logs", "risk_scores", "alerts", "analysis_runs",
    "devices", "device_heartbeats", "endpoint_events", "enrollment_tokens", "alembic_version",
}


def test_fresh_database_upgrades_to_full_schema(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path/'fresh.db'}")
    assert upgrade_database(engine) == "upgraded"
    assert set(inspect(engine).get_table_names()) == ALL_TABLES
    assert upgrade_database(engine) == "upgraded"  # idempotent


def test_adopts_pre_alembic_v1_database_without_data_loss(tmp_path: Path):
    """A v1 database (v1 schema, no alembic_version) is stamped at the baseline and
    upgraded, keeping every existing row."""
    db = tmp_path / "legacy.db"
    engine = make_engine(f"sqlite:///{db}")
    # Build the authentic v1 schema by running only migration 0001, then drop the
    # alembic_version table to reproduce a pre-Alembic v1.0.0 database.
    upgrade_database(engine, "0001")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (username, full_name, email, department, role, home_country, home_city, shift) "
                          "VALUES ('u1', 'User One', 'u1@x.test', 'Eng', 'developer', 'IN', 'Pune', 'day')"))
        conn.execute(text("INSERT INTO analysis_runs (status, logs_analyzed, alerts_created, parameters, metrics) "
                          "VALUES ('completed', 1, 1, '{}', '{}')"))
        conn.execute(text("INSERT INTO access_logs (user_id, timestamp, ip_address, country, city, device, action, resource, resource_sensitivity, status) "
                          "VALUES (1, '2026-10-01 10:00:00', '10.0.0.1', 'IN', 'Pune', 'Chrome', 'login', '/auth/sso', 'public', 'success')"))
        conn.execute(text("INSERT INTO alerts (log_id, user_id, severity, risk_score, title, description, status) "
                          "VALUES (1, 1, 'high', 60, 'Test', 'desc', 'resolved')"))

    assert "alembic_version" not in inspect(engine).get_table_names()
    action = upgrade_database(engine)
    assert "adopted" in action

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM alerts")).scalar() == 1
        # the pre-existing alert gets the new default source
        assert conn.execute(text("SELECT source FROM alerts WHERE id=1")).scalar() == "access_log"
        assert conn.execute(text("SELECT status FROM alerts WHERE id=1")).scalar() == "resolved"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
    assert set(inspect(engine).get_table_names()) == ALL_TABLES


def test_partial_schema_is_refused(tmp_path: Path):
    """A half-migrated v1 database (some legacy tables, no alembic_version) is not
    silently migrated."""
    engine = make_engine(f"sqlite:///{tmp_path/'partial.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    with pytest.raises(RuntimeError, match="partial v1 schema"):
        upgrade_database(engine)
