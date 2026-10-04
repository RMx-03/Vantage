import os
from pathlib import Path

import pytest

os.environ.setdefault("TRACE_EXPORT_ENABLED", "false")
os.environ.setdefault("AUTH_JWT_SECRET", "test-only-secret-that-is-long-enough-32b")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
# Reuse-detection tests replay a token immediately and expect theft to be
# detected. The grace window is exercised explicitly in test_refresh_grace.py.
os.environ.setdefault("AUTH_REFRESH_REUSE_GRACE_SECONDS", "0")
os.environ.setdefault(
    "TELEMETRY_USER_SALT", "test-only-salt-that-is-at-least-32-bytes-long"
)
# The suite registers many accounts from one apparent source; the tests that
# exercise throttling lower this themselves.
os.environ.setdefault("AUTH_REGISTER_MAX_ATTEMPTS", "100000")
os.environ.setdefault("AUTH_EMAIL_SOURCE_MAX_ATTEMPTS", "100000")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://vantage_runtime:vantage_runtime@localhost:5433/vantage_test",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql+psycopg://vantage_owner:vantage_owner@localhost:5433/vantage_test",
)
os.environ.setdefault("VANTAGE_RUNTIME_DB_ROLE", "vantage_runtime")


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root, resolved from this file's location on disk."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def _only_the_test_database() -> None:
    """Stop the whole run before any test can write to a non-test database.

    Checks the URL the application resolves, which may come from backend/.env,
    not just the DATABASE_URL environment variable.
    """
    from app.db.session import get_database_url
    from tests.db_guard import require_test_database

    try:
        require_test_database(get_database_url())
    except RuntimeError as error:
        pytest.exit(str(error), returncode=2)


@pytest.fixture
def make_user():
    """Create a real account and return its public id.

    Research runs must belong to a real user since the ownership foreign key
    landed, so every integration test that needs an owner goes through here
    rather than repeating the setup.
    """
    from uuid import uuid4

    from app.repositories.users import UserRepository

    def _make(prefix: str = "user"):
        return (
            UserRepository()
            .create(
                email=f"{prefix}-{uuid4().hex}@example.com",
                password_hash="h",
                password_algo="argon2id",
            )
            .public_id
        )

    return _make
