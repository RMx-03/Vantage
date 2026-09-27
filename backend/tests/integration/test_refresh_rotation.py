from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.auth_models import RefreshTokenRow
from app.db.session import SessionFactory
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

pytestmark = pytest.mark.integration


@pytest.fixture()
def user_id() -> int:
    return UserRepository().create(
        email=f"rt-{uuid4().hex}@example.com", password_hash="h", password_algo="argon2id"
    ).id


@pytest.fixture()
def repo() -> RefreshTokenRepository:
    return RefreshTokenRepository()


def test_rotation_returns_a_new_token(repo: RefreshTokenRepository, user_id: int) -> None:
    raw, _ = repo.issue(user_id=user_id)
    result = repo.rotate(raw)
    assert result.outcome == "rotated"
    assert result.raw_token is not None
    assert result.raw_token != raw
    assert result.user_id == user_id


def test_rotation_keeps_the_family(repo: RefreshTokenRepository, user_id: int) -> None:
    raw, family = repo.issue(user_id=user_id)
    rotated = repo.rotate(raw)
    assert rotated.raw_token is not None
    second = repo.rotate(rotated.raw_token)
    assert second.outcome == "rotated"
    with SessionFactory() as session:
        families = set(
            session.execute(
                select(RefreshTokenRow.family_id).where(RefreshTokenRow.user_id == user_id)
            ).scalars()
        )
    assert families == {family}


def test_replaying_a_rotated_token_is_detected_as_reuse(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    raw, _ = repo.issue(user_id=user_id)
    repo.rotate(raw)
    replay = repo.rotate(raw)
    assert replay.outcome == "reused"
    assert replay.raw_token is None


def test_reuse_revokes_the_whole_family(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    # The point of reuse detection: a stolen token must not leave the thief's
    # newer token usable. Everything in the lineage dies.
    raw, _ = repo.issue(user_id=user_id)
    rotated = repo.rotate(raw)
    assert rotated.raw_token is not None
    repo.rotate(raw)  # replay triggers detection
    after = repo.rotate(rotated.raw_token)
    assert after.outcome in {"reused", "not_found"}
    with SessionFactory() as session:
        live = session.execute(
            select(RefreshTokenRow).where(
                RefreshTokenRow.user_id == user_id, RefreshTokenRow.revoked_at.is_(None)
            )
        ).scalars().all()
    assert live == []


def test_unknown_token_is_not_found(repo: RefreshTokenRepository) -> None:
    assert repo.rotate("never-issued-token").outcome == "not_found"


def test_expired_token_is_rejected(repo: RefreshTokenRepository, user_id: int) -> None:
    raw, _ = repo.issue(user_id=user_id)
    with SessionFactory() as session, session.begin():
        row = session.execute(
            select(RefreshTokenRow).where(RefreshTokenRow.user_id == user_id)
        ).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert repo.rotate(raw).outcome == "expired"


def test_revoke_all_kills_every_family(repo: RefreshTokenRepository, user_id: int) -> None:
    first, _ = repo.issue(user_id=user_id)
    second, _ = repo.issue(user_id=user_id)
    repo.revoke_all_for_user(user_id, reason="password_change")
    assert repo.rotate(first).outcome in {"reused", "not_found"}
    assert repo.rotate(second).outcome in {"reused", "not_found"}
