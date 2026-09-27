from uuid import uuid4

import pytest

from app.domain.auth import AUTH_INVALID, AUTH_RATE_LIMITED, AUTH_WEAK_PASSWORD
from app.domain.errors import VantageError
from app.services.auth import AuthService

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def service() -> AuthService:
    return AuthService()


def _email() -> str:
    return f"svc-{uuid4().hex}@example.com"


def test_registration_creates_an_account(service: AuthService) -> None:
    outcome = service.register(email=_email(), password=PASSWORD)
    assert outcome.created is True
    assert outcome.user_public_id is not None


def test_registering_an_existing_address_reports_not_created_without_raising(
    service: AuthService,
) -> None:
    # Enumeration resistance: the caller cannot tell these apart, so the route
    # must be able to return an identical response either way.
    email = _email()
    service.register(email=email, password=PASSWORD)
    outcome = service.register(email=email, password=PASSWORD)
    assert outcome.created is False


def test_registration_rejects_a_weak_password(service: AuthService) -> None:
    with pytest.raises(VantageError) as excinfo:
        service.register(email=_email(), password="short")
    assert excinfo.value.code == AUTH_WEAK_PASSWORD


def test_registration_normalizes_the_email(service: AuthService) -> None:
    email = _email()
    service.register(email=email.upper(), password=PASSWORD)
    session = service.login(email=email, password=PASSWORD)
    assert session.access_token


def test_login_returns_a_session(service: AuthService) -> None:
    email = _email()
    service.register(email=email, password=PASSWORD)
    session = service.login(email=email, password=PASSWORD)
    assert session.access_token
    assert session.refresh_token
    assert session.expires_in == 900
    assert session.email_verified is False


def test_login_with_a_wrong_password_is_rejected(service: AuthService) -> None:
    email = _email()
    service.register(email=email, password=PASSWORD)
    with pytest.raises(VantageError) as excinfo:
        service.login(email=email, password="a completely different one")
    assert excinfo.value.code == AUTH_INVALID


def test_login_for_an_unknown_account_is_rejected_identically(
    service: AuthService,
) -> None:
    with pytest.raises(VantageError) as excinfo:
        service.login(email=_email(), password=PASSWORD)
    assert excinfo.value.code == AUTH_INVALID


def test_repeated_failures_trip_the_rate_limiter(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    email = _email()
    service.register(email=email, password=PASSWORD)
    for _ in range(3):
        with pytest.raises(VantageError):
            service.login(email=email, password="wrong password here")
    with pytest.raises(VantageError) as excinfo:
        service.login(email=email, password=PASSWORD)
    assert excinfo.value.code == AUTH_RATE_LIMITED
