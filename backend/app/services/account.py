"""Account lifecycle: verification, recovery, and password change.

Two rules run through all of it:

1. Nothing here reveals whether an address is registered. `request_password_reset`
   and `resend_verification` return normally for unknown addresses and send
   nothing.
2. Mail failure never rolls back account state. An unverified account the user
   can resend from is recoverable; a discarded registration is not.
"""

import logging
from uuid import UUID

from app.core.config import settings
from app.core.security.passwords import PASSWORD_ALGO, hash_password, verify_password
from app.core.security.policy import normalize_email, validate_password
from app.domain.auth import AUTH_INVALID, AUTH_RATE_LIMITED, INVALID_CREDENTIALS_MESSAGE
from app.domain.errors import VantageError
from app.repositories.auth_attempts import AuthAttemptRepository, attempt_key
from app.repositories.email_tokens import EmailTokenRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.services.email import EmailDeliveryError, EmailSender, get_email_sender
from app.services.email.templates import (
    duplicate_registration_message,
    password_reset_message,
    verification_message,
)

logger = logging.getLogger(__name__)

_VERIFICATION = "email_verification"
_RESET = "password_reset"


class AccountService:
    def __init__(
        self,
        users: UserRepository | None = None,
        email_tokens: EmailTokenRepository | None = None,
        refresh_tokens: RefreshTokenRepository | None = None,
        email_sender: EmailSender | None = None,
        attempts: AuthAttemptRepository | None = None,
    ) -> None:
        self._users = users or UserRepository()
        self._attempts = attempts or AuthAttemptRepository()
        self._tokens = email_tokens or EmailTokenRepository()
        self._refresh = refresh_tokens or RefreshTokenRepository()
        self._sender = email_sender or get_email_sender()

    def send_verification(self, user_id: int, email: str) -> None:
        """Mint and send a verification link. Never raises on delivery failure."""
        self._tokens.invalidate_outstanding(user_id, purpose=_VERIFICATION)
        raw = self._tokens.issue(
            user_id=user_id,
            purpose=_VERIFICATION,
            email=email,
            ttl_seconds=settings.EMAIL_VERIFICATION_TTL_SECONDS,
        )
        self._deliver(verification_message(email, raw))

    def verify_email(self, raw_token: str) -> None:
        consumed = self._tokens.consume(raw_token, purpose=_VERIFICATION)
        if consumed is None:
            raise VantageError(
                code=AUTH_INVALID,
                safe_message="This link is invalid or has expired. Request a new one.",
            )
        self._users.mark_email_verified(consumed.user_id)

    def resend_verification(self, email: str) -> None:
        user = self._users.find_by_email(normalize_email(email))
        if user is None or user.email_verified:
            return  # Silent: the caller must not learn either fact.
        self.send_verification(user.id, user.email)

    def request_password_reset(self, email: str) -> None:
        user = self._users.find_by_email(normalize_email(email))
        if user is None:
            return  # Silent.

        self._tokens.invalidate_outstanding(user.id, purpose=_RESET)
        raw = self._tokens.issue(
            user_id=user.id,
            purpose=_RESET,
            email=user.email,
            ttl_seconds=settings.PASSWORD_RESET_TTL_SECONDS,
        )
        self._deliver(password_reset_message(user.email, raw))

    def reset_password(self, raw_token: str, new_password: str) -> None:
        invalid = VantageError(
            code=AUTH_INVALID,
            safe_message="This link is invalid or has expired. Request a new one.",
        )
        # Validate before spending the single-use link. Consuming first meant a
        # rejected weak password burned the link and sent the user back to
        # their inbox.
        pending = self._tokens.peek(raw_token, purpose=_RESET)
        if pending is None:
            raise invalid
        checked = validate_password(new_password, email=pending.email)

        # consume() locks the row, so of two concurrent submissions exactly one
        # wins; the other is told the link is spent.
        consumed = self._tokens.consume(raw_token, purpose=_RESET)
        if consumed is None:
            raise invalid
        self._users.update_password(
            consumed.user_id,
            password_hash=hash_password(checked),
            password_algo=PASSWORD_ALGO,
        )
        # A reset is the response to a possible compromise. Every existing
        # session dies, including any the attacker holds.
        self._refresh.revoke_all_for_user(consumed.user_id, reason="password_reset")

        # Proving control of the mailbox also proves the address works.
        self._users.mark_email_verified(consumed.user_id)

    def change_password(
        self, user_public_id: UUID, current_password: str, new_password: str
    ) -> None:
        # Guesses at the current password are throttled exactly like login.
        # This endpoint checks the same secret, and a stolen access token would
        # otherwise buy unlimited attempts at it.
        key = attempt_key("change-password", str(user_public_id))
        if self._attempts.is_rate_limited(
            key,
            window_seconds=settings.AUTH_LOGIN_WINDOW_SECONDS,
            max_attempts=settings.AUTH_LOGIN_MAX_ATTEMPTS,
        ):
            raise VantageError(
                code=AUTH_RATE_LIMITED,
                safe_message="Too many attempts. Try again shortly.",
                retryable=True,
            )

        user = self._users.find_by_public_id(user_public_id)
        if user is None or not verify_password(current_password, user.password_hash):
            self._attempts.record(key)
            raise VantageError(
                code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE
            )
        self._attempts.clear(key)

        checked = validate_password(new_password, email=user.email)
        self._users.update_password(
            user.id, password_hash=hash_password(checked), password_algo=PASSWORD_ALGO
        )
        self._refresh.revoke_all_for_user(user.id, reason="password_change")

    def notify_duplicate_registration(self, email: str) -> None:
        """Tell the existing account holder that someone tried to register.

        This is the other half of enumeration resistance: the registration form
        returns an identical response either way, and the person actually told
        is the account owner, not whoever submitted the form.
        """
        self._deliver(duplicate_registration_message(email))

    def _deliver(self, message: object) -> None:
        try:
            self._sender.send(message)  # type: ignore[arg-type]
        except EmailDeliveryError:
            # Logged, not raised. The token is already persisted, so the user
            # can request another message once delivery recovers.
            logger.error(
                "email.delivery_failed flow=%s", getattr(message, "subject", "?")
            )
