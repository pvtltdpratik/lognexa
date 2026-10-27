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
    version: str = "1.0.0"
    database_url: str = Field(
        default="postgresql+psycopg2://lognexa:change-me@localhost:5432/lognexa",
        description="SQLAlchemy database URL",
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    random_seed: int = 42

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
