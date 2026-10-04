from uuid import uuid4

import pytest

from app.repositories.email_tokens import EmailTokenRepository
from app.repositories.users import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def user_id() -> int:
    return (
        UserRepository()
        .create(
            email=f"et-{uuid4().hex}@example.com",
            password_hash="h",
            password_algo="argon2id",
        )
        .id
    )


@pytest.fixture()
def repo() -> EmailTokenRepository:
    return EmailTokenRepository()


def test_issued_token_can_be_consumed(repo: EmailTokenRepository, user_id: int) -> None:
    raw = repo.issue(
        user_id=user_id, purpose="email_verification", email="a@b.com", ttl_seconds=3600
    )
    consumed = repo.consume(raw, purpose="email_verification")
    assert consumed is not None
    assert consumed.user_id == user_id


def test_token_is_single_use(repo: EmailTokenRepository, user_id: int) -> None:
    raw = repo.issue(
        user_id=user_id, purpose="email_verification", email="a@b.com", ttl_seconds=3600
    )
    repo.consume(raw, purpose="email_verification")
    assert repo.consume(raw, purpose="email_verification") is None


def test_token_cannot_be_used_for_another_purpose(
    repo: EmailTokenRepository, user_id: int
) -> None:
    # A verification token must not double as a password reset.
    raw = repo.issue(
        user_id=user_id, purpose="email_verification", email="a@b.com", ttl_seconds=3600
    )
    assert repo.consume(raw, purpose="password_reset") is None


def test_expired_token_is_refused(repo: EmailTokenRepository, user_id: int) -> None:
    raw = repo.issue(
        user_id=user_id, purpose="password_reset", email="a@b.com", ttl_seconds=0
    )
    assert repo.consume(raw, purpose="password_reset") is None


def test_unknown_token_is_refused(repo: EmailTokenRepository) -> None:
    assert repo.consume("never-issued", purpose="password_reset") is None


def test_invalidate_outstanding_kills_prior_tokens(
    repo: EmailTokenRepository, user_id: int
) -> None:
    # Requesting a second reset must retire the first link.
    first = repo.issue(
        user_id=user_id, purpose="password_reset", email="a@b.com", ttl_seconds=3600
    )
    repo.invalidate_outstanding(user_id, purpose="password_reset")
    assert repo.consume(first, purpose="password_reset") is None
