"""Access-token encoding and opaque-token minting.

Access tokens are stateless JWTs with a short lifetime; the lifetime is the
revocation strategy, which is why nothing is stored server-side. Refresh tokens
are opaque random strings, stored only as SHA-256 digests. A fast hash is
correct for them precisely because they already carry 256 bits of entropy: a
slow KDF protects low-entropy secrets and would only add latency here.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import UUID

import jwt

from app.core.config import settings
from app.domain.auth import AUTH_INVALID, AUTH_TOKEN_EXPIRED
from app.domain.errors import VantageError

_ALGORITHM = "HS256"
_ACCESS_TYPE = "access"


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: UUID
    email_verified: bool
    jti: str


def issue_access_token(
    *,
    user_public_id: UUID,
    email_verified: bool,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Return (encoded token, lifetime in seconds)."""
    issued_at = now or datetime.now(UTC)
    ttl = settings.AUTH_ACCESS_TOKEN_TTL_SECONDS
    payload = {
        "sub": str(user_public_id),
        "iss": settings.AUTH_JWT_ISSUER,
        "aud": settings.AUTH_JWT_AUDIENCE,
        "typ": _ACCESS_TYPE,
        # Carried in the claim so the verification gate costs no database read
        # on the hot path. The cost is that a newly verified account keeps a
        # stale `ev` until its access token expires.
        "ev": email_verified,
        "jti": secrets.token_urlsafe(16),
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET, algorithm=_ALGORITHM), ttl


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.AUTH_JWT_SECRET,
            algorithms=[_ALGORITHM],
            audience=settings.AUTH_JWT_AUDIENCE,
            issuer=settings.AUTH_JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise VantageError(
            code=AUTH_TOKEN_EXPIRED,
            safe_message="Your session has expired.",
        ) from None
    except jwt.InvalidTokenError:
        raise VantageError(
            code=AUTH_INVALID,
            safe_message="Authentication credentials are invalid.",
        ) from None

    # Reject token-type confusion explicitly: a refresh-typed JWT must never
    # authenticate a request even though it verifies under the same secret.
    if payload.get("typ") != _ACCESS_TYPE:
        raise VantageError(
            code=AUTH_INVALID,
            safe_message="Authentication credentials are invalid.",
        )

    try:
        subject = UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        raise VantageError(
            code=AUTH_INVALID,
            safe_message="Authentication credentials are invalid.",
        ) from None

    return AccessTokenClaims(
        subject=subject,
        email_verified=bool(payload.get("ev", False)),
        jti=str(payload.get("jti", "")),
    )


def hash_opaque_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def mint_opaque_token() -> tuple[str, str]:
    """Return (raw token to hand to the client, digest to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_opaque_token(raw)
