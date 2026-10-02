from uuid import uuid4

import pytest

from app.domain.auth import AUTH_INVALID
from app.domain.errors import VantageError
from app.services.auth import AuthService

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def service() -> AuthService:
    return AuthService()


def _registered(service: AuthService) -> tuple[str, object]:
    email = f"sess-{uuid4().hex}@example.com"
    service.register(email=email, password=PASSWORD)
    return email, service.login(email=email, password=PASSWORD)


def test_refresh_returns_a_new_access_and_refresh_token(service: AuthService) -> None:
    _, session = _registered(service)
    refreshed = service.refresh(session.refresh_token)
    assert refreshed.refresh_token != session.refresh_token
    assert refreshed.user_public_id == session.user_public_id


def test_replayed_refresh_token_is_rejected(service: AuthService) -> None:
    _, session = _registered(service)
    service.refresh(session.refresh_token)
    with pytest.raises(VantageError) as excinfo:
        service.refresh(session.refresh_token)
    assert excinfo.value.code == AUTH_INVALID


def test_reuse_invalidates_the_newer_token_too(service: AuthService) -> None:
    _, session = _registered(service)
    rotated = service.refresh(session.refresh_token)
    with pytest.raises(VantageError):
        service.refresh(session.refresh_token)
    with pytest.raises(VantageError):
        service.refresh(rotated.refresh_token)


def test_unknown_refresh_token_is_rejected(service: AuthService) -> None:
    with pytest.raises(VantageError):
        service.refresh("never-issued")


def test_logout_invalidates_the_token(service: AuthService) -> None:
    _, session = _registered(service)
    service.logout(session.refresh_token)
    with pytest.raises(VantageError):
        service.refresh(session.refresh_token)


def test_logout_all_invalidates_every_session(service: AuthService) -> None:
    email = f"sess-{uuid4().hex}@example.com"
    service.register(email=email, password=PASSWORD)
    first = service.login(email=email, password=PASSWORD)
    second = service.login(email=email, password=PASSWORD)
    service.logout_all(first.user_public_id)
    for session in (first, second):
        with pytest.raises(VantageError):
            service.refresh(session.refresh_token)


def _set_status(email: str, status: str) -> None:
    from sqlalchemy import update

    from app.db.auth_models import UserRow
    from app.db.session import SessionFactory

    with SessionFactory() as db, db.begin():
        db.execute(update(UserRow).where(UserRow.email == email).values(status=status))


def test_a_disabled_account_cannot_refresh(service: AuthService) -> None:
    """Refresh must re-check account state, not just token validity.

    Access tokens last 15 minutes, so revocation depends on refresh refusing to
    mint more. Without this check a disabled account keeps issuing access tokens
    indefinitely, and disabling an account accomplishes nothing.
    """
    email, session = _registered(service)
    _set_status(email, "disabled")

    with pytest.raises(VantageError):
        service.refresh(session.refresh_token)


def test_a_locked_account_cannot_refresh(service: AuthService) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.auth_models import UserRow
    from app.db.session import SessionFactory

    email, session = _registered(service)
    with SessionFactory() as db, db.begin():
        db.execute(
            update(UserRow)
            .where(UserRow.email == email)
            .values(locked_until=datetime.now(UTC) + timedelta(minutes=30))
        )

    with pytest.raises(VantageError):
        service.refresh(session.refresh_token)
