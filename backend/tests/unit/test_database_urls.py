import pytest

from app.db.urls import normalize_database_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgres://user:password@host.example:5432/database?sslmode=require",
            "postgresql+psycopg://user:password@host.example:5432/database?sslmode=require",
        ),
        (
            "postgresql://user:password@host.example:5432/database",
            "postgresql+psycopg://user:password@host.example:5432/database",
        ),
        (
            "postgresql+psycopg://user:password@host.example:5432/database",
            "postgresql+psycopg://user:password@host.example:5432/database",
        ),
        (
            "postgresql+asyncpg://user:password@host.example:5432/database",
            "postgresql+asyncpg://user:password@host.example:5432/database",
        ),
        (
            "sqlite+pysqlite:///local.db",
            "sqlite+pysqlite:///local.db",
        ),
    ],
)
def test_normalize_database_url(url: str, expected: str) -> None:
    assert normalize_database_url(url) == expected
