from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.security import HTTPAuthorizationCredentials
import pytest

from app.api import deps
from app.core.security.tokens import issue_access_token
from app.domain.errors import VantageError
from app.repositories.research_runs import ResearchRunRepository


@pytest.mark.anyio
async def test_missing_credentials_is_typed_auth_error() -> None:
    with pytest.raises(VantageError) as exc_info:
        await deps.get_current_user(None)
    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.safe_message == "Authentication is required."


@pytest.mark.anyio
async def test_empty_credentials_is_typed_auth_error() -> None:
    with pytest.raises(VantageError) as exc_info:
        await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
        )
    assert exc_info.value.code == "AUTH_REQUIRED"


@pytest.mark.anyio
async def test_native_access_token_authenticates() -> None:
    user_id = uuid4()
    token, _ = issue_access_token(user_public_id=user_id, email_verified=True)
    user = await deps.get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )
    assert user.id == user_id


@pytest.mark.anyio
async def test_tampered_native_token_is_rejected() -> None:
    token, _ = issue_access_token(user_public_id=uuid4(), email_verified=True)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(VantageError) as exc_info:
        await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered)
        )
    assert exc_info.value.code == "AUTH_INVALID"


@pytest.mark.anyio
async def test_expired_native_token_reports_expiry_not_invalid() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    token, _ = issue_access_token(user_public_id=uuid4(), email_verified=True, now=past)

    with pytest.raises(VantageError) as excinfo:
        await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )

    assert excinfo.value.code == "AUTH_TOKEN_EXPIRED"


def test_repository_dependency_returns_owner_scoped_repository() -> None:
    assert isinstance(deps.get_research_repository(), ResearchRunRepository)


def test_an_authenticated_user_must_state_whether_it_is_verified() -> None:
    """email_verified gates research runs, so it must never default open.

    A default of True meant any code that built an AuthenticatedUser and forgot
    the field produced a verified user, silently bypassing the gate. Every other
    part of the auth layer fails closed; this must too.
    """
    from uuid import uuid4

    from pydantic import ValidationError

    from app.api.deps import AuthenticatedUser

    with pytest.raises(ValidationError):
        AuthenticatedUser(id=uuid4())  # type: ignore[call-arg]
