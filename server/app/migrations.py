"""Programmatic Alembic upgrade that also adopts pre-Alembic databases.

v1.0.0 created tables with ``Base.metadata.create_all`` and had no
``alembic_version`` table. Such a database already matches revision 0001, so
it is *stamped* at 0001 (no SQL executed against existing tables) and then
upgraded normally. Nothing is ever dropped or reset.
"""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.config import SERVER_DIR

log = logging.getLogger("lognexa.migrations")
BASELINE = "0001"
LEGACY_TABLES = {"users", "access_logs", "risk_scores", "alerts", "analysis_runs"}


def alembic_config(engine: Engine) -> Config:
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    cfg.attributes["database_url"] = engine.url.render_as_string(hide_password=False)
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_database(engine: Engine, revision: str = "head") -> str:
    """Bring ``engine``'s database to ``revision``; returns the action taken."""
    tables = set(inspect(engine).get_table_names())
    cfg = alembic_config(engine)
    action = "upgraded"
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        if "alembic_version" not in tables and LEGACY_TABLES <= tables:
            log.info("Adopting pre-Alembic database: stamping revision %s", BASELINE)
            command.stamp(cfg, BASELINE)
            action = "adopted legacy schema and upgraded"
        elif "alembic_version" not in tables and tables & LEGACY_TABLES:
            raise RuntimeError(
                f"Database has a partial v1 schema ({sorted(tables & LEGACY_TABLES)}); refusing to migrate automatically."
            )
        command.upgrade(cfg, revision)
    return action
