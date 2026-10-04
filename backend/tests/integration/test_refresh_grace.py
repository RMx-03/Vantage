"""The reuse grace window for rotated refresh tokens.

A page reload can land after the server rotated the cookie but before the
browser stored the new one, so the next refresh presents the old token. Without
a grace window that looks exactly like theft and signs the user out everywhere.
The window must stay narrow enough that it never helps an actual thief.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.db.auth_models import RefreshTokenRow
from app.db.session import SessionFactory
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

pytestmark = pytest.mark.integration

GRACE = 10


@pytest.fixture()
def repo(monkeypatch: pytest.MonkeyPatch) -> RefreshTokenRepository:
    monkeypatch.setattr(settings, "AUTH_REFRESH_REUSE_GRACE_SECONDS", GRACE)
    return RefreshTokenRepository()


@pytest.fixture()
def user_id() -> int:
    return (
        UserRepository()
        .create(
            email=f"grace-{uuid4().hex}@example.com",
            password_hash="h",
            password_algo="argon2id",
        )
        .id
    )


def _live_tokens(user_id: int) -> int:
    with SessionFactory() as db:
        return len(
            db.execute(
                select(RefreshTokenRow).where(
                    RefreshTokenRow.user_id == user_id,
                    RefreshTokenRow.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )


def test_replay_just_after_rotation_is_honoured(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    """The lost-response case: rotated, successor never used, replayed at once."""
    raw, _ = repo.issue(user_id=user_id)
    repo.rotate(raw)

    replay = repo.rotate(raw)

    assert replay.outcome == "rotated"
    assert replay.raw_token is not None and replay.raw_token != raw
    assert _live_tokens(user_id) >= 1, "grace must not revoke the family"


def test_grace_is_single_use(repo: RefreshTokenRepository, user_id: int) -> None:
    """Repeated replays of one token must not mint session after session."""
    raw, _ = repo.issue(user_id=user_id)
    repo.rotate(raw)
    repo.rotate(raw)

    second = repo.rotate(raw)

    assert second.outcome == "reused"
    assert _live_tokens(user_id) == 0


def test_no_grace_once_the_successor_has_been_used(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    """The theft case: the real client already moved on, then the old token
    reappears. That is reuse, whatever the timing."""
    raw, _ = repo.issue(user_id=user_id)
    first = repo.rotate(raw)
    assert first.raw_token is not None
    repo.rotate(first.raw_token)

    replay = repo.rotate(raw)

    assert replay.outcome == "reused"
    assert _live_tokens(user_id) == 0


def test_no_grace_outside_the_window(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    raw, _ = repo.issue(user_id=user_id)
    repo.rotate(raw)
    with SessionFactory() as db, db.begin():
        db.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.user_id == user_id)
            .where(RefreshTokenRow.revoked_reason == "rotated")
            .values(revoked_at=datetime.now(UTC) - timedelta(seconds=GRACE + 1))
        )

    assert repo.rotate(raw).outcome == "reused"


def test_no_grace_for_a_token_revoked_by_logout(
    repo: RefreshTokenRepository, user_id: int
) -> None:
    """Grace exists for lost rotations only. A signed-out token stays dead."""
    raw, _ = repo.issue(user_id=user_id)
    repo.revoke(raw, reason="logout")

    assert repo.rotate(raw).outcome != "rotated"


def test_zero_grace_disables_it(
    repo: RefreshTokenRepository, user_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTH_REFRESH_REUSE_GRACE_SECONDS", 0)
    raw, _ = repo.issue(user_id=user_id)
    repo.rotate(raw)

    assert repo.rotate(raw).outcome == "reused"
