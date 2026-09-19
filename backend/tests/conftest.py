import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("TRACE_EXPORT_ENABLED", "false")


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root, resolved from this file's location on disk."""
    return Path(__file__).resolve().parents[2]
