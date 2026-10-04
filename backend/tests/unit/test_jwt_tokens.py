from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security.tokens import (
    decode_access_token,
    hash_opaque_token,
    issue_access_token,
    mint_opaque_token,
)
from app.domain.auth import AUTH_INVALID, AUTH_TOKEN_EXPIRED
from app.domain.errors import VantageError


def test_issued_token_round_trips() -> None:
    user_id = uuid4()
    token, expires_in = issue_access_token(user_public_id=user_id, email_verified=True)
    claims = decode_access_token(token)
    assert claims.subject == user_id
    assert claims.email_verified is True
    assert expires_in == 900


def test_each_token_has_a_unique_jti() -> None:
    user_id = uuid4()
    first, _ = issue_access_token(user_public_id=user_id, email_verified=False)
    second, _ = issue_access_token(user_public_id=user_id, email_verified=False)
    assert decode_access_token(first).jti != decode_access_token(second).jti


def test_expired_token_is_rejected_as_expired() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    token, _ = issue_access_token(user_public_id=uuid4(), email_verified=True, now=past)
    with pytest.raises(VantageError) as excinfo:
        decode_access_token(token)
    assert excinfo.value.code == AUTH_TOKEN_EXPIRED


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": settings.AUTH_JWT_ISSUER,
            "aud": settings.AUTH_JWT_AUDIENCE,
            "typ": "access",
            "ev": True,
            "jti": "forged",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "an-entirely-different-secret-value-32b",
        algorithm="HS256",
    )
    with pytest.raises(VantageError) as excinfo:
        decode_access_token(forged)
    assert excinfo.value.code == AUTH_INVALID


def test_token_with_wrong_audience_is_rejected() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": settings.AUTH_JWT_ISSUER,
            "aud": "some-other-api",
            "typ": "access",
            "ev": True,
            "jti": "x",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.AUTH_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(VantageError):
        decode_access_token(token)


def test_refresh_typed_token_is_not_accepted_as_an_access_token() -> None:
    # Token-type confusion: a refresh JWT must never authenticate a request.
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": settings.AUTH_JWT_ISSUER,
            "aud": settings.AUTH_JWT_AUDIENCE,
            "typ": "refresh",
            "ev": True,
            "jti": "x",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.AUTH_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(VantageError):
        decode_access_token(token)


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(VantageError):
        decode_access_token("not.a.jwt")


def test_opaque_token_is_high_entropy_and_hash_matches() -> None:
    raw, digest = mint_opaque_token()
    assert len(raw) >= 43  # 32 bytes base64url-encoded
    assert digest == hash_opaque_token(raw)
    assert len(digest) == 64  # sha256 hex


def test_two_opaque_tokens_differ() -> None:
    assert mint_opaque_token()[0] != mint_opaque_token()[0]
