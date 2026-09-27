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
    assert attempt_key("login:email", "a@b.com") == attempt_key("login:email", "a@b.com")


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
