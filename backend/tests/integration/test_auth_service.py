from uuid import uuid4

import pytest

from app.domain.auth import (
    AUTH_ACCOUNT_LOCKED,
    AUTH_INVALID,
    AUTH_RATE_LIMITED,
    AUTH_WEAK_PASSWORD,
)
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


def test_a_password_needing_nfkc_normalization_can_log_in(
    service: AuthService,
) -> None:
    """Register normalizes before hashing; login must normalize before verifying.

    U+FF21 FULLWIDTH LATIN CAPITAL A normalizes to "A". If login verifies the
    raw string, any password typed through an IME or containing ligatures or
    full-width characters is registered successfully and can then never be
    used again.
    """
    email = _email()
    password = "\uff21bcdefghijklm"

    service.register(email=email, password=password)
    session = service.login(email=email, password=password)

    assert session.access_token


def test_password_length_ceiling_is_enforced_on_login(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Argon2 CPU ceiling must exist on the unauthenticated path too.

    validate_password bounds length at 128, but login never called it, so an
    arbitrarily long password reached the hasher on an endpoint that needs no
    credentials to invoke. Asserting the hasher was never entered is the point:
    rejecting late still burns the CPU the ceiling exists to protect.
    """
    email = _email()
    service.register(email=email, password=PASSWORD)

    calls: list[int] = []
    import app.services.auth as auth_module

    real_verify = auth_module.verify_password

    def counting_verify(password: str, encoded_hash: str) -> bool:
        calls.append(len(password))
        return real_verify(password, encoded_hash)

    monkeypatch.setattr(auth_module, "verify_password", counting_verify)

    with pytest.raises(VantageError) as excinfo:
        service.login(email=email, password="a" * 5000)

    assert excinfo.value.code == AUTH_INVALID
    assert calls == [], "an over-length password reached the Argon2 hasher"


def test_one_source_cannot_rate_limit_a_victim_elsewhere(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Throttling must be scoped per source, not per email alone.

    With an email-only key, anyone who knows an address can spend the whole
    window on it and lock the real owner out of logging in at all — a denial of
    service that needs no credentials and renews indefinitely.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    email = _email()
    service.register(email=email, password=PASSWORD)

    for _ in range(5):
        with pytest.raises(VantageError):
            service.login(
                email=email, password="wrong password here", ip_hash="attacker-ip"
            )

    session = service.login(email=email, password=PASSWORD, ip_hash="victim-ip")
    assert session.access_token


def test_successful_login_clears_the_attempt_window(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    email = _email()
    service.register(email=email, password=PASSWORD)

    for _ in range(2):
        with pytest.raises(VantageError):
            service.login(email=email, password="wrong password here", ip_hash="ip-a")

    service.login(email=email, password=PASSWORD, ip_hash="ip-a")

    # Two more failures would trip the limit if the earlier ones still counted.
    for _ in range(2):
        with pytest.raises(VantageError) as excinfo:
            service.login(email=email, password="wrong password here", ip_hash="ip-a")
        assert excinfo.value.code == AUTH_INVALID


def test_a_locked_account_is_indistinguishable_without_the_password(
    service: AuthService,
) -> None:
    """Lock state must not be observable to someone who lacks the password.

    Returning AUTH_ACCOUNT_LOCKED before verifying credentials told any caller
    which addresses are registered, and that branch recorded no attempt, so the
    probe was not even rate limited.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.auth_models import UserRow
    from app.db.session import SessionFactory

    email = _email()
    service.register(email=email, password=PASSWORD)
    with SessionFactory() as db, db.begin():
        db.execute(
            update(UserRow)
            .where(UserRow.email == email)
            .values(locked_until=datetime.now(UTC) + timedelta(minutes=30))
        )

    with pytest.raises(VantageError) as locked:
        service.login(email=email, password="wrong password here", ip_hash="probe")
    with pytest.raises(VantageError) as unknown:
        service.login(email=_email(), password="wrong password here", ip_hash="probe")

    assert locked.value.code == unknown.value.code
    assert str(locked.value) == str(unknown.value)


def test_the_real_owner_still_learns_the_account_is_locked(
    service: AuthService,
) -> None:
    """Knowing the password is what earns the accurate message."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.auth_models import UserRow
    from app.db.session import SessionFactory

    email = _email()
    service.register(email=email, password=PASSWORD)
    with SessionFactory() as db, db.begin():
        db.execute(
            update(UserRow)
            .where(UserRow.email == email)
            .values(locked_until=datetime.now(UTC) + timedelta(minutes=30))
        )

    with pytest.raises(VantageError) as excinfo:
        service.login(email=email, password=PASSWORD, ip_hash="owner")
    assert excinfo.value.code == AUTH_ACCOUNT_LOCKED


def test_registration_is_rate_limited_per_source(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registration runs a 19 MiB Argon2 hash and needs no credentials.

    FastAPI offloads sync endpoints to a 40-slot threadpool, so an unthrottled
    /register lets one caller drive roughly 760 MiB of concurrent hashing on a
    512 MB dyno — the very memory ceiling those parameters were chosen for —
    besides creating unbounded accounts.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 3)
    # The attempts table outlives a single test run, so a fixed key would carry
    # counts forward from previous runs and trip on the first call.
    source = f"flooder-{uuid4().hex}"

    for _ in range(3):
        service.register(email=_email(), password=PASSWORD, ip_hash=source)

    with pytest.raises(VantageError) as excinfo:
        service.register(email=_email(), password=PASSWORD, ip_hash=source)
    assert excinfo.value.code == AUTH_RATE_LIMITED


def test_registration_from_another_source_is_unaffected(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 2)

    noisy = f"flooder-{uuid4().hex}"
    for _ in range(3):
        try:
            service.register(email=_email(), password=PASSWORD, ip_hash=noisy)
        except VantageError:
            pass

    outcome = service.register(
        email=_email(), password=PASSWORD, ip_hash=f"quiet-{uuid4().hex}"
    )
    assert outcome.created is True
