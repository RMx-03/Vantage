"""Migration 20261115_0005: multi-source snapshot columns and the provider cache."""

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import ResearchRunRow, ResearchSnapshotRow, ResearchSourceRow
from app.db.session import SessionFactory, get_database_url
from app.db.urls import normalize_database_url
from tests.db_guard import require_test_database

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "20260920_0004"
SNAPSHOT_COLUMNS = {"providers", "context_bars", "fundamentals", "macro"}
SOURCE_COLUMNS = {"summary", "details"}


def _migration_database_url() -> str:
    """The URL the Alembic subprocess connects to, mirroring migrations/env.py."""
    from app.core.config import settings

    return normalize_database_url(
        os.environ.get("MIGRATION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or getattr(settings, "MIGRATION_DATABASE_URL", None)
        or getattr(settings, "DATABASE_URL", None)
        or ""
    )


def _alembic(*args: str) -> None:
    # Downgrading is destructive: refuse unless both the runtime URL and the
    # URL Alembic will really use name the test database.
    require_test_database(get_database_url())
    require_test_database(_migration_database_url())
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=str(BACKEND),
        env=os.environ.copy(),
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _columns(table: str) -> set[str]:
    with SessionFactory() as session:
        rows = session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'vantage_app' AND table_name = :t"
            ),
            {"t": table},
        )
        return {row[0] for row in rows}


def _table_exists(table: str) -> bool:
    with SessionFactory() as session:
        return (
            session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'vantage_app' AND table_name = :t"
                ),
                {"t": table},
            ).scalar()
            == 1
        )


def _check_constraint_exists() -> bool:
    with SessionFactory() as session:
        return (
            session.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE "
                    "conname = 'ck_research_sources_source_type'"
                )
            ).scalar()
            == 1
        )


def test_0005_downgrade_and_upgrade_round_trip() -> None:
    # This downgrades the shared test database, so the suite must stay serial.
    try:
        _alembic("downgrade", PREVIOUS_REVISION)
        assert not _table_exists("provider_cache")
        assert not SNAPSHOT_COLUMNS & _columns("research_snapshots")
        assert not SOURCE_COLUMNS & _columns("research_sources")
        assert not _check_constraint_exists()

        _alembic("upgrade", "head")
        assert _table_exists("provider_cache")
        assert SNAPSHOT_COLUMNS <= _columns("research_snapshots")
        assert SOURCE_COLUMNS <= _columns("research_sources")
        assert _check_constraint_exists()
    finally:
        _alembic("upgrade", "head")


def test_source_type_check_rejects_unknown(make_user) -> None:
    now = datetime.now(UTC)
    owner = make_user("check")
    with SessionFactory() as session:
        run = ResearchRunRow(
            user_id=owner,
            symbol="AAPL",
            workflow_status="running",
            created_at=now,
            started_at=now,
            response_schema_version="v",
            workflow_version="v",
            metrics_version="v",
            policy_version="v",
            code_version="v",
        )
        session.add(run)
        session.flush()
        snapshot = ResearchSnapshotRow(
            run_id=run.id,
            user_id=owner,
            symbol="AAPL",
            market_provider="fixture",
            window_start=now,
            window_end=now,
            as_of=now,
            retrieved_at=now,
            content_hash="h",
            market_content_hash="h",
            news_provider="fixture",
            news_retrieved_at=now,
            news_quality="ok",
            price_bars=[],
            quality={},
        )
        session.add(snapshot)
        session.flush()
        session.add(
            ResearchSourceRow(
                snapshot_id=snapshot.id,
                evidence_id="e1",
                source_type="filing",
                provider="fixture",
                title="ok",
                retrieved_at=now,
            )
        )
        session.flush()  # an allowed type is accepted
        session.add(
            ResearchSourceRow(
                snapshot_id=snapshot.id,
                evidence_id="e2",
                source_type="press_release",
                provider="fixture",
                title="bad",
                retrieved_at=now,
            )
        )
        with pytest.raises(IntegrityError) as excinfo:
            session.flush()
        assert "ck_research_sources_source_type" in str(excinfo.value)
        session.rollback()


def test_runtime_role_can_write_and_purge_cache() -> None:
    expected = os.environ.get("VANTAGE_RUNTIME_DB_ROLE", "").strip()
    with SessionFactory() as session:
        current = session.execute(text("SELECT current_user")).scalar()
        if not expected or current != expected:
            pytest.skip("database is not connected as the least-privilege runtime role")
        key = uuid4().hex
        session.execute(
            text(
                "INSERT INTO vantage_app.provider_cache "
                "(provider, cache_key, content_hash, valid_for_date, payload, "
                "retrieved_at) VALUES ('fixture', :k, 'h', :d, '{}'::jsonb, now())"
            ),
            {"k": key, "d": date(2026, 11, 13)},
        )
        immutable = session.execute(
            text(
                "SELECT immutable FROM vantage_app.provider_cache WHERE cache_key = :k"
            ),
            {"k": key},
        ).scalar()
        assert immutable is False
        deleted = session.execute(
            text("DELETE FROM vantage_app.provider_cache WHERE cache_key = :k"),
            {"k": key},
        )
        assert deleted.rowcount == 1
        session.rollback()
