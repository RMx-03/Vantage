from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import SessionFactory
from app.providers.cache import compute_content_hash
from app.repositories.provider_cache import PostgresProviderCache

pytestmark = pytest.mark.integration

DAY = date(2026, 11, 13)


@pytest.fixture()
def provider() -> Iterator[str]:
    name = f"test-{uuid4().hex}"
    yield name
    with SessionFactory() as session, session.begin():
        session.execute(
            text("DELETE FROM vantage_app.provider_cache WHERE provider = :p"),
            {"p": name},
        )


def _insert(provider: str, key: str, age_days: int, immutable: bool) -> None:
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO vantage_app.provider_cache "
                "(provider, cache_key, valid_for_date, content_hash, payload, "
                "retrieved_at, immutable) VALUES (:p, :k, :d, 'h', "
                "CAST('{}' AS jsonb), now() - make_interval(days => :age), :i)"
            ),
            {"p": provider, "k": key, "d": DAY, "age": age_days, "i": immutable},
        )


def _count(provider: str, key: str) -> int:
    with SessionFactory() as session:
        return session.execute(
            text(
                "SELECT count(*) FROM vantage_app.provider_cache "
                "WHERE provider = :p AND cache_key = :k"
            ),
            {"p": provider, "k": key},
        ).scalar_one()


def test_round_trip(provider: str) -> None:
    cache = PostgresProviderCache()
    now = datetime.now(UTC)
    stored = cache.put(provider, "k", DAY, {"a": [1, 2]}, now)
    fetched = cache.get(provider, "k", DAY)
    assert fetched is not None
    assert fetched.payload == {"a": [1, 2]}
    assert fetched.content_hash == stored.content_hash
    assert fetched.retrieved_at == now
    assert cache.get(provider, "k", date(2026, 11, 12)) is None
    assert cache.get(provider, "other", DAY) is None


def test_upsert_replaces_payload_and_hash(provider: str) -> None:
    cache = PostgresProviderCache()
    now = datetime.now(UTC)
    cache.put(provider, "k", DAY, {"v": 1}, now)
    cache.put(provider, "k", DAY, {"v": 2}, now)
    fetched = cache.get(provider, "k", DAY)
    assert fetched is not None
    assert fetched.payload == {"v": 2}
    assert fetched.content_hash == compute_content_hash({"v": 2})
    assert _count(provider, "k") == 1


def test_purge_removes_old_mutable_rows_only(provider: str) -> None:
    _insert(provider, "old-mutable", 8, False)
    _insert(provider, "old-immutable", 8, True)
    _insert(provider, "recent", 1, False)
    PostgresProviderCache().put(provider, "new", DAY, {}, datetime.now(UTC))
    assert _count(provider, "old-mutable") == 0
    assert _count(provider, "old-immutable") == 1
    assert _count(provider, "recent") == 1
    assert _count(provider, "new") == 1


def test_second_put_inside_interval_does_not_purge(provider: str) -> None:
    ticks = iter([1000.0, 1010.0, 5000.0])
    cache = PostgresProviderCache(
        purge_interval_seconds=3600, clock=lambda: next(ticks)
    )
    now = datetime.now(UTC)
    cache.put(provider, "first", DAY, {}, now)
    _insert(provider, "old-mutable", 8, False)
    cache.put(provider, "second", DAY, {}, now)
    assert _count(provider, "old-mutable") == 1
    cache.put(provider, "third", DAY, {}, now + timedelta(seconds=1))
    assert _count(provider, "old-mutable") == 0


def test_runtime_role_can_read_and_write(provider: str) -> None:
    with SessionFactory() as session:
        assert session.execute(text("SELECT current_user")).scalar_one() == (
            "vantage_runtime"
        )
    cache = PostgresProviderCache()
    cache.put(provider, "k", DAY, {"ok": True}, datetime.now(UTC), immutable=True)
    fetched = cache.get(provider, "k", DAY)
    assert fetched is not None and fetched.payload == {"ok": True}
