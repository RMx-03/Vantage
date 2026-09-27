from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.users import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def repo() -> UserRepository:
    return UserRepository()


def _email() -> str:
    return f"user-{uuid4().hex}@example.com"


def test_created_user_is_retrievable_by_email(repo: UserRepository) -> None:
    email = _email()
    created = repo.create(email=email, password_hash="$argon2id$fake", password_algo="argon2id")
    found = repo.find_by_email(email)
    assert found is not None
    assert found.public_id == created.public_id
    assert found.email_verified is False
    assert found.status == "active"


def test_lookup_is_none_for_unknown_email(repo: UserRepository) -> None:
    assert repo.find_by_email(_email()) is None


def test_duplicate_email_raises(repo: UserRepository) -> None:
    email = _email()
    repo.create(email=email, password_hash="h", password_algo="argon2id")
    with pytest.raises(Exception):
        repo.create(email=email, password_hash="h", password_algo="argon2id")


def test_failed_logins_lock_the_account_at_the_threshold(repo: UserRepository) -> None:
    user = repo.create(email=_email(), password_hash="h", password_algo="argon2id")
    for _ in range(3):
        repo.record_failed_login(user.id, lock_after=3, lock_for_seconds=900)
    refreshed = repo.find_by_public_id(user.public_id)
    assert refreshed is not None
    assert refreshed.locked_until is not None
    assert refreshed.locked_until > datetime.now(UTC)


def test_successful_login_clears_the_failure_counter(repo: UserRepository) -> None:
    user = repo.create(email=_email(), password_hash="h", password_algo="argon2id")
    repo.record_failed_login(user.id, lock_after=10, lock_for_seconds=900)
    repo.record_successful_login(user.id)
    refreshed = repo.find_by_public_id(user.public_id)
    assert refreshed is not None
    assert refreshed.locked_until is None


def test_marking_email_verified_is_visible(repo: UserRepository) -> None:
    user = repo.create(email=_email(), password_hash="h", password_algo="argon2id")
    repo.mark_email_verified(user.id)
    refreshed = repo.find_by_public_id(user.public_id)
    assert refreshed is not None
    assert refreshed.email_verified is True
