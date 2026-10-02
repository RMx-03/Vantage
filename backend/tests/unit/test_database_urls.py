import pytest

from app.db.session import MAX_OVERFLOW, POOL_SIZE, engine
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
            "postgresql+psycopg://user:password@host.example:5432/database?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:password@host.example:5432/database",
            "postgresql+psycopg://user:password@host.example:5432/database?sslmode=require",
        ),
        (
            "postgresql+asyncpg://user:password@host.example:5432/database",
            "postgresql+asyncpg://user:password@host.example:5432/database?sslmode=require",
        ),
        (
            "sqlite+pysqlite:///local.db",
            "sqlite+pysqlite:///local.db",
        ),
        (
            "postgres://u:p@ec2.amazonaws.com/db",
            "postgresql+psycopg://u:p@ec2.amazonaws.com/db?sslmode=require",
        ),
        (
            "postgres://u:p@host.example/db?sslmode=verify-full",
            "postgresql+psycopg://u:p@host.example/db?sslmode=verify-full",
        ),
        (
            "postgres://u:p@host.example/db?sslmode=disable",
            "postgresql+psycopg://u:p@host.example/db?sslmode=disable",
        ),
        (
            "postgres://u:p@host.example:5432/db?custom=1&sslmode=require",
            "postgresql+psycopg://u:p@host.example:5432/db?custom=1&sslmode=require",
        ),
        (
            "postgres://u:p@host.example:5432/db?custom=1",
            "postgresql+psycopg://u:p@host.example:5432/db?custom=1&sslmode=require",
        ),
    ],
)
def test_normalize_database_url(url: str, expected: str) -> None:
    assert normalize_database_url(url) == expected


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "::1", "postgres", "db", "host.docker.internal"],
)
def test_local_hosts_are_not_forced_to_ssl(host: str) -> None:
    formatted_host = f"[{host}]" if ":" in host else host
    result = normalize_database_url(f"postgres://u:p@{formatted_host}:5432/db")
    assert "sslmode" not in result
    assert result == f"postgresql+psycopg://u:p@{formatted_host}:5432/db"


def test_empty_database_url_raises_value_error() -> None:
    with pytest.raises(ValueError):
        normalize_database_url("")


def test_whitespace_database_url_raises_value_error() -> None:
    with pytest.raises(ValueError):
        normalize_database_url("   ")


def test_database_engine_pool_bounds() -> None:
    assert POOL_SIZE == 5
    assert MAX_OVERFLOW == 2
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 2
    assert engine.pool._recycle == 280
    assert engine.pool._pre_ping is True
