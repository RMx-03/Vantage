from uuid import uuid4

import pytest

from app.domain.auth import AUTH_INVALID, AUTH_WEAK_PASSWORD
from app.domain.errors import VantageError
from app.repositories.users import UserRepository
from app.services.account import AccountService
from app.services.auth import AuthService
from app.services.email.sender import EmailDeliveryError, EmailMessage

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a totally different passphrase"


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FailingSender:
    def send(self, message: EmailMessage) -> None:
        raise EmailDeliveryError("provider down")


@pytest.fixture()
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture()
def accounts(sender: RecordingSender) -> AccountService:
    return AccountService(email_sender=sender)


def _token_from(message: EmailMessage) -> str:
    return message.text.split("token=")[1].split()[0].strip()


def _new_user(accounts: AccountService) -> tuple[str, int]:
    email = f"acct-{uuid4().hex}@example.com"
    AuthService().register(email=email, password=PASSWORD)
    stored = UserRepository().find_by_email(email)
    assert stored is not None
    accounts.send_verification(stored.id, email)
    return email, stored.id


def test_verification_marks_the_account_verified(
    accounts: AccountService, sender: RecordingSender
) -> None:
    email, user_id = _new_user(accounts)
    accounts.verify_email(_token_from(sender.sent[-1]))
    stored = UserRepository().find_by_email(email)
    assert stored is not None and stored.email_verified is True


def test_verification_token_cannot_be_replayed(
    accounts: AccountService, sender: RecordingSender
) -> None:
    _new_user(accounts)
    token = _token_from(sender.sent[-1])
    accounts.verify_email(token)
    with pytest.raises(VantageError) as excinfo:
        accounts.verify_email(token)
    assert excinfo.value.code == AUTH_INVALID


def test_reset_request_for_an_unknown_address_is_silent(
    accounts: AccountService, sender: RecordingSender
) -> None:
    # No raise, no mail. The caller cannot tell the address is unregistered.
    accounts.request_password_reset(f"nobody-{uuid4().hex}@example.com")
    assert sender.sent == []


def test_reset_changes_the_password(
    accounts: AccountService, sender: RecordingSender
) -> None:
    email, _ = _new_user(accounts)
    accounts.request_password_reset(email)
    accounts.reset_password(_token_from(sender.sent[-1]), NEW_PASSWORD)

    AuthService().login(email=email, password=NEW_PASSWORD)
    with pytest.raises(VantageError):
        AuthService().login(email=email, password=PASSWORD)


def test_reset_revokes_every_existing_session(
    accounts: AccountService, sender: RecordingSender
) -> None:
    # If the reset was triggered because the account was compromised, leaving
    # the attacker's session alive defeats the entire point.
    email, _ = _new_user(accounts)
    auth = AuthService()
    session = auth.login(email=email, password=PASSWORD)
    accounts.request_password_reset(email)
    accounts.reset_password(_token_from(sender.sent[-1]), NEW_PASSWORD)
    with pytest.raises(VantageError):
        auth.refresh(session.refresh_token)


def test_reset_rejects_a_weak_new_password(
    accounts: AccountService, sender: RecordingSender
) -> None:
    email, _ = _new_user(accounts)
    accounts.request_password_reset(email)
    with pytest.raises(VantageError) as excinfo:
        accounts.reset_password(_token_from(sender.sent[-1]), "short")
    assert excinfo.value.code == AUTH_WEAK_PASSWORD


def test_change_password_requires_the_current_one(accounts: AccountService) -> None:
    email, _ = _new_user(accounts)
    stored = UserRepository().find_by_email(email)
    assert stored is not None
    with pytest.raises(VantageError):
        accounts.change_password(stored.public_id, "not the password", NEW_PASSWORD)


def test_change_password_succeeds_with_the_current_one(
    accounts: AccountService,
) -> None:
    email, _ = _new_user(accounts)
    stored = UserRepository().find_by_email(email)
    assert stored is not None
    accounts.change_password(stored.public_id, PASSWORD, NEW_PASSWORD)
    AuthService().login(email=email, password=NEW_PASSWORD)


def test_registration_survives_a_mail_outage() -> None:
    # Losing an account because the provider was down would be a worse failure
    # than an unverified account.
    failing = AccountService(email_sender=FailingSender())
    email = f"outage-{uuid4().hex}@example.com"
    AuthService().register(email=email, password=PASSWORD)
    stored = UserRepository().find_by_email(email)
    assert stored is not None
    failing.send_verification(stored.id, email)  # must not raise
    assert UserRepository().find_by_email(email) is not None


def test_a_rejected_weak_password_does_not_burn_the_reset_link(
    accounts: AccountService, sender: RecordingSender
) -> None:
    """The link is single-use, so it must only be spent on a password that is
    actually accepted. Consuming it first meant one typo of a short password
    forced the user back to their inbox for a new link."""
    email, _ = _new_user(accounts)
    accounts.request_password_reset(email)
    token = _token_from(sender.sent[-1])

    with pytest.raises(VantageError) as excinfo:
        accounts.reset_password(token, "short")
    assert excinfo.value.code == AUTH_WEAK_PASSWORD

    accounts.reset_password(token, NEW_PASSWORD)
    AuthService().login(email=email, password=NEW_PASSWORD)


def test_change_password_limits_guesses_at_the_current_password(
    accounts: AccountService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whoever holds an access token, including a stolen one, must not get
    unlimited guesses at the current password. Login was throttled and this
    endpoint, which checks the same secret, was not."""
    from app.core.config import settings
    from app.domain.auth import AUTH_RATE_LIMITED

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    email, _ = _new_user(accounts)
    stored = UserRepository().find_by_email(email)
    assert stored is not None

    for _ in range(3):
        with pytest.raises(VantageError) as wrong:
            accounts.change_password(stored.public_id, "not the password", NEW_PASSWORD)
        assert wrong.value.code == AUTH_INVALID

    with pytest.raises(VantageError) as limited:
        accounts.change_password(stored.public_id, PASSWORD, NEW_PASSWORD)
    assert limited.value.code == AUTH_RATE_LIMITED


def test_a_successful_password_change_clears_the_guess_count(
    accounts: AccountService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    email, _ = _new_user(accounts)
    stored = UserRepository().find_by_email(email)
    assert stored is not None

    for _ in range(2):
        with pytest.raises(VantageError):
            accounts.change_password(stored.public_id, "not the password", NEW_PASSWORD)
    accounts.change_password(stored.public_id, PASSWORD, NEW_PASSWORD)

    for _ in range(2):
        with pytest.raises(VantageError) as wrong:
            accounts.change_password(stored.public_id, "still wrong", PASSWORD)
        assert wrong.value.code == AUTH_INVALID
