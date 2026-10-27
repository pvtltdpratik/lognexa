"""Application settings loaded from environment variables / server/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOGNEXA_", env_file=SERVER_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Lognexa API"
    version: str = "2.0.0"
    database_url: str = Field(
        default="postgresql+psycopg2://lognexa:change-me@localhost:5432/lognexa",
        description="SQLAlchemy database URL",
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    random_seed: int = 42

    # --- endpoint monitoring / access control ------------------------------------
    # Bearer tokens for humans using the dashboard. Empty = that role is disabled;
    # endpoint APIs fail closed (503) when neither token is configured.
    admin_token: str = Field(default="", repr=False)
    analyst_token: str = Field(default="", repr=False)
    # Reject agent traffic over plain HTTP unless it comes from the loopback interface.
    agent_require_https: bool = True
    # Honour X-Forwarded-Proto / X-Forwarded-For (only behind a trusted TLS proxy).
    trust_proxy_headers: bool = False
    heartbeat_interval_seconds: int = Field(default=60, ge=10, le=3600)
    # A device is "stale" after 3 missed heartbeats and "offline" after 10.
    stale_after_seconds: int = Field(default=180, ge=30)
    offline_after_seconds: int = Field(default=600, ge=60)
    max_events_per_batch: int = Field(default=500, ge=1, le=5000)
    heartbeats_kept_per_device: int = Field(default=200, ge=10)
    endpoint_alert_threshold: float = Field(default=50.0, ge=1, le=100)
    correlation_window_minutes: int = Field(default=30, ge=1, le=1440)

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite(cls, v: str) -> str:
        # Resolve relative SQLite paths against server/ so the DB file is the same
        # no matter which directory uvicorn / pytest is started from.
        prefix = "sqlite:///"
        if v.startswith(prefix) and v != "sqlite:///:memory:":
            path = Path(v[len(prefix):])
            if not path.is_absolute():
                return prefix + (SERVER_DIR / path).resolve().as_posix()
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
