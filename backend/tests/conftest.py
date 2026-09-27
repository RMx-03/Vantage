import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("TRACE_EXPORT_ENABLED", "false")
os.environ.setdefault("AUTH_JWT_SECRET", "test-only-secret-that-is-long-enough-32b")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
# The suite registers many accounts from one apparent source; the tests that
# exercise throttling lower this themselves.
os.environ.setdefault("AUTH_REGISTER_MAX_ATTEMPTS", "100000")
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
