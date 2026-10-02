from uuid import uuid4

import pytest

from app.repositories.auth_attempts import AuthAttemptRepository, attempt_key

pytestmark = pytest.mark.integration


@pytest.fixture()
def repo() -> AuthAttemptRepository:
    return AuthAttemptRepository()


def _key() -> str:
    return attempt_key("login:email", f"user-{uuid4().hex}@example.com")


def test_key_does_not_contain_the_raw_value() -> None:
    # Storing the raw address would turn this table into a directory of who
    # has tried to sign in.
    key = attempt_key("login:email", "operator@example.com")
    assert "operator@example.com" not in key
    assert key.startswith("login:email:")


def test_same_value_produces_a_stable_key() -> None:
    assert attempt_key("login:email", "a@b.com") == attempt_key(
        "login:email", "a@b.com"
    )


def test_fresh_key_is_not_limited(repo: AuthAttemptRepository) -> None:
    assert repo.is_rate_limited(_key(), window_seconds=900, max_attempts=3) is False


def test_attempts_accumulate(repo: AuthAttemptRepository) -> None:
    key = _key()
    for _ in range(3):
        repo.record(key)
    assert repo.count_within(key, window_seconds=900) == 3


def test_limit_trips_at_the_threshold(repo: AuthAttemptRepository) -> None:
    key = _key()
    for _ in range(3):
        repo.record(key)
    assert repo.is_rate_limited(key, window_seconds=900, max_attempts=3) is True


def test_attempts_outside_the_window_do_not_count(repo: AuthAttemptRepository) -> None:
    key = _key()
    for _ in range(5):
        repo.record(key)
    assert repo.count_within(key, window_seconds=0) == 0


def test_keys_are_independent(repo: AuthAttemptRepository) -> None:
    first, second = _key(), _key()
    for _ in range(5):
        repo.record(first)
    assert repo.is_rate_limited(second, window_seconds=900, max_attempts=3) is False


def test_purge_removes_old_rows(repo: AuthAttemptRepository) -> None:
    key = _key()
    repo.record(key)
    assert repo.purge_older_than(0) >= 1
    assert repo.count_within(key, window_seconds=900) == 0


def _insert_attempt_at(key: str, seconds_ago: int) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.auth_models import AuthAttemptRow
    from app.db.session import SessionFactory

    with SessionFactory() as db, db.begin():
        db.add(
            AuthAttemptRow(
                key=key,
                occurred_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
            )
        )


def _rows_for(key: str) -> int:
    from sqlalchemy import func, select

    from app.db.auth_models import AuthAttemptRow
    from app.db.session import SessionFactory

    with SessionFactory() as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(AuthAttemptRow)
                .where(AuthAttemptRow.key == key)
            ).scalar_one()
        )


def test_recording_purges_that_keys_expired_attempts(
    repo: AuthAttemptRepository,
) -> None:
    """Writes must bound the table without an external scheduler.

    purge_older_than existed but nothing in the application called it, so every
    failed login and registration was kept forever and the count(*) on the hot
    path degraded as the table grew.
    """
    key = _key()
    for _ in range(5):
        _insert_attempt_at(key, seconds_ago=10 * 24 * 3600)

    repo.record(key)

    assert _rows_for(key) == 1


def test_recording_keeps_attempts_still_inside_the_window(
    repo: AuthAttemptRepository,
) -> None:
    """Purging must never erase evidence a live rate limit depends on."""
    key = _key()
    _insert_attempt_at(key, seconds_ago=60)

    repo.record(key)

    assert _rows_for(key) == 2


def test_the_sweep_removes_expired_attempts_across_all_keys() -> None:
    """Keys that are never written again are only reclaimed by the sweep."""
    from scripts.purge_auth_attempts import sweep

    abandoned = _key()
    _insert_attempt_at(abandoned, seconds_ago=10 * 24 * 3600)

    removed = sweep()

    assert removed >= 1
    assert _rows_for(abandoned) == 0
