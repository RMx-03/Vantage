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
from app.core.security.policy import (
    MAX_PASSWORD_LENGTH,
    normalize_email,
    normalize_password,
    validate_password,
)
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
from app.repositories.users import StoredUser, UserRepository

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
            return RegistrationOutcome(
                created=False, user_public_id=None, email=normalized
            )

        user = self._users.create(
            email=normalized,
            password_hash=hash_password(checked),
            password_algo=PASSWORD_ALGO,
        )
        return RegistrationOutcome(
            created=True, user_public_id=user.public_id, email=normalized
        )

    @staticmethod
    def _require_usable_account(user: StoredUser) -> None:
        """Reject an account that is disabled or inside a lockout window.

        Shared by login and refresh deliberately: when only login checked this,
        a disabled account kept minting access tokens through refresh forever.
        """
        if user.status != "active" or (
            user.locked_until is not None and user.locked_until > datetime.now(UTC)
        ):
            raise VantageError(
                code=AUTH_ACCOUNT_LOCKED,
                safe_message="This account is temporarily locked.",
                retryable=True,
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
        # Scope throttling to the source as well as the address. Keyed on email
        # alone, anyone who knows an address could spend the window on it and
        # lock the real owner out — a denial of service needing no credentials.
        key = attempt_key("login", f"{normalized}|{ip_hash or 'unknown-source'}")

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

        candidate = normalize_password(password)

        # Bound the work before anything expensive runs. Argon2 is deliberately
        # costly, and login needs no credentials to invoke, so an unbounded
        # password here is a free way to burn dyno CPU. Reported as AUTH_INVALID
        # so it stays indistinguishable from a wrong password.
        if len(candidate) > MAX_PASSWORD_LENGTH:
            self._attempts.record(key)
            raise VantageError(
                code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE
            )

        user = self._users.find_by_email(normalized)

        if user is None:
            # Cost parity with the wrong-password path.
            dummy_verify()
            self._attempts.record(key)
            raise VantageError(
                code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE
            )

        self._require_usable_account(user)

        if not verify_password(candidate, user.password_hash):
            self._attempts.record(key)
            self._users.record_failed_login(
                user.id,
                lock_after=_LOCK_AFTER_FAILURES,
                lock_for_seconds=_LOCK_FOR_SECONDS,
            )
            raise VantageError(
                code=AUTH_INVALID, safe_message=INVALID_CREDENTIALS_MESSAGE
            )

        # Opportunistic upgrade when parameters change. The plaintext is only
        # available here, at the moment of a successful login.
        if needs_rehash(user.password_hash):
            self._users.update_password(
                user.id,
                password_hash=hash_password(candidate),
                password_algo=PASSWORD_ALGO,
            )

        self._attempts.clear(key)
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

    def refresh(
        self,
        raw_refresh_token: str,
        *,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> IssuedSession:
        result = self._refresh.rotate(
            raw_refresh_token, user_agent=user_agent, ip_hash=ip_hash
        )

        if (
            result.outcome != "rotated"
            or result.raw_token is None
            or result.user_id is None
        ):
            # not_found, expired and reused are all the same to the caller. A
            # distinct "your session was revoked for reuse" message would tell
            # an attacker their stolen token was detected.
            raise VantageError(
                code=AUTH_INVALID,
                safe_message="Your session is no longer valid. Sign in again.",
            )

        user = self._users_by_internal_id(result.user_id)

        # Re-check account state on every rotation. Access tokens live 15
        # minutes, so refusing to mint more is the only thing that makes
        # disabling or locking an account take effect at all.
        try:
            self._require_usable_account(user)
        except VantageError:
            self._refresh.revoke_all_for_user(user.id, reason="account_unusable")
            raise

        access_token, expires_in = issue_access_token(
            user_public_id=user.public_id, email_verified=user.email_verified
        )
        return IssuedSession(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=result.raw_token,
            user_public_id=user.public_id,
            email_verified=user.email_verified,
        )

    def logout(self, raw_refresh_token: str) -> None:
        """Revoke one session. Idempotent and never reveals token validity."""
        self._refresh.revoke(raw_refresh_token, reason="logout")

    def logout_all(self, user_public_id: UUID) -> None:
        user = self._users.find_by_public_id(user_public_id)
        if user is None:
            return
        self._refresh.revoke_all_for_user(user.id, reason="logout_all")

    def _users_by_internal_id(self, user_id: int) -> StoredUser:
        from app.db.auth_models import UserRow
        from app.db.session import SessionFactory
        from app.repositories.users import _to_stored

        with SessionFactory() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                raise VantageError(
                    code=AUTH_INVALID,
                    safe_message="Your session is no longer valid. Sign in again.",
                )
            return _to_stored(row)
