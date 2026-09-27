"""Authentication use cases.

Two behaviours here are deliberate and easy to "simplify" into bugs:

1. `register` never tells the caller whether the address already existed.
   Returning a conflict would let anyone enumerate registered users.
2. `login` runs a dummy Argon2 verification when no account matches, so the
   unknown-account path costs the same as the wrong-password path. Skipping it
   reintroduces a timing oracle.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.core.security.passwords import (
    PASSWORD_ALGO,
    dummy_verify,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.security.policy import normalize_email, validate_password
from app.core.security.tokens import issue_access_token
from app.domain.auth import (
    AUTH_ACCOUNT_LOCKED,
    AUTH_INVALID,
    AUTH_RATE_LIMITED,
    INVALID_CREDENTIALS_MESSAGE,
)
from app.domain.errors import VantageError
from app.repositories.auth_attempts import AuthAttemptRepository, attempt_key
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository

# Account lockout escalates beyond the per-key rate limit; it survives an
# attacker rotating source addresses.
_LOCK_AFTER_FAILURES = 10
_LOCK_FOR_SECONDS = 900


@dataclass(frozen=True)
class RegistrationOutcome:
    created: bool
    user_public_id: UUID | None
    email: str


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    expires_in: int
    refresh_token: str
    user_public_id: UUID
    email_verified: bool


class AuthService:
    def __init__(
        self,
        users: UserRepository | None = None,
        refresh_tokens: RefreshTokenRepository | None = None,
        attempts: AuthAttemptRepository | None = None,
    ) -> None:
        self._users = users or UserRepository()
        self._refresh = refresh_tokens or RefreshTokenRepository()
        self._attempts = attempts or AuthAttemptRepository()

    def register(self, *, email: str, password: str) -> RegistrationOutcome:
        normalized = normalize_email(email)
        checked = validate_password(password, email=normalized)

        if self._users.find_by_email(normalized) is not None:
            # Do not raise. The route returns the same body either way; Phase 2C
            # sends the existing account a notice instead.
            return RegistrationOutcome(created=False, user_public_id=None, email=normalized)

        user = self._users.create(
            email=normalized,
            password_hash=hash_password(checked),
            password_algo=PASSWORD_ALGO,
        )
        return RegistrationOutcome(
            created=True, user_public_id=user.public_id, email=normalized
        )

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> IssuedSession:
        normalized = normalize_email(email)
        key = attempt_key("login:email", normalized)

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

        user = self._users.find_by_email(normalized)

        if user is None:
            # Cost parity with the wrong-password path.
            dummy_verify()
            self._attempts.record(key)
            raise VantageError(code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE)

        if user.status != "active" or (
            user.locked_until is not None and user.locked_until > datetime.now(UTC)
        ):
            raise VantageError(
                code=AUTH_ACCOUNT_LOCKED,
                safe_message="This account is temporarily locked.",
                retryable=True,
            )

        if not verify_password(password, user.password_hash):
            self._attempts.record(key)
            self._users.record_failed_login(
                user.id, lock_after=_LOCK_AFTER_FAILURES, lock_for_seconds=_LOCK_FOR_SECONDS
            )
            raise VantageError(code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE)

        # Opportunistic upgrade when parameters change. The plaintext is only
        # available here, at the moment of a successful login.
        if needs_rehash(user.password_hash):
            self._users.update_password(
                user.id, password_hash=hash_password(password), password_algo=PASSWORD_ALGO
            )

        self._users.record_successful_login(user.id)
        raw_refresh, _ = self._refresh.issue(
            user_id=user.id, user_agent=user_agent, ip_hash=ip_hash
        )
        access_token, expires_in = issue_access_token(
            user_public_id=user.public_id, email_verified=user.email_verified
        )
        return IssuedSession(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=raw_refresh,
            user_public_id=user.public_id,
            email_verified=user.email_verified,
        )
