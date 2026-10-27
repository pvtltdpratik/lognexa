"""Database URL normalisation for hosted PostgreSQL connection strings."""

import pytest

from app.config import Settings


@pytest.mark.parametrize("given", [
    "postgres://u:p@db.example.test:5432/app?sslmode=require",
    "postgresql://u:p@db.example.test:5432/app?sslmode=require",
    "postgresql+psycopg2://u:p@db.example.test:5432/app?sslmode=require",
    '  "postgresql://u:p@db.example.test:5432/app?sslmode=require"  ',
])
def test_postgres_urls_use_the_installed_driver(given):
    url = Settings(database_url=given).database_url
    assert url == "postgresql+psycopg2://u:p@db.example.test:5432/app?sslmode=require"


def test_sqlite_url_is_left_alone_but_anchored():
    url = Settings(database_url="sqlite:///./x.db").database_url
    assert url.startswith("sqlite:///") and url.endswith("/server/x.db")
