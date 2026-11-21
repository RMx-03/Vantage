"""Migration 20261122_0006: the nullable crosscheck column on research_snapshots."""

import pytest

from tests.integration.test_migration_0005 import _alembic, _columns

pytestmark = pytest.mark.integration


def test_0006_downgrade_and_upgrade_round_trip() -> None:
    # Downgrades the shared test database, so the suite must stay serial.
    try:
        _alembic("downgrade", "20261115_0005")
        assert "crosscheck" not in _columns("research_snapshots")
        _alembic("upgrade", "head")
        assert "crosscheck" in _columns("research_snapshots")
    finally:
        _alembic("upgrade", "head")
