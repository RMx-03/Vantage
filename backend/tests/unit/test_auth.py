from unittest.mock import MagicMock
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import deps
from app.domain.errors import VantageError
from app.repositories.research_runs import ResearchRunRepository


def test_missing_credentials_is_typed_auth_error() -> None:
    with pytest.raises(VantageError) as exc_info:
        asyncio.run(deps.get_current_user(None))
    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.safe_message == "Authentication is required."


def test_provider_failure_is_typed_auth_error(monkeypatch) -> None:
    client = MagicMock()
    client.auth.get_user.side_effect = RuntimeError("token-secret-must-not-leak")
    monkeypatch.setattr(deps, "supabase_client", client)
    credentials = MagicMock(credentials="token-secret-must-not-leak")
    with pytest.raises(VantageError) as exc_info:
        asyncio.run(deps.get_current_user(credentials))
    assert exc_info.value.code == "AUTH_INVALID"
    assert "token-secret" not in exc_info.value.safe_message


def test_valid_credentials_return_only_the_authenticated_user_id(monkeypatch) -> None:
    user_id = uuid4()
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=str(user_id), email="must-not-enter-domain@example.com")
    )
    monkeypatch.setattr(deps, "supabase_client", client)
    credentials = MagicMock(credentials="valid-token")

    authenticated = asyncio.run(deps.get_current_user(credentials))

    assert authenticated.id == user_id
    assert authenticated.model_dump() == {"id": user_id}


def test_malformed_authenticated_user_is_rejected(monkeypatch) -> None:
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="not-a-uuid")
    )
    monkeypatch.setattr(deps, "supabase_client", client)

    with pytest.raises(VantageError) as exc_info:
        asyncio.run(deps.get_current_user(MagicMock(credentials="valid-token")))

    assert exc_info.value.code == "AUTH_INVALID"


def test_missing_authenticated_user_is_rejected(monkeypatch) -> None:
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(user=None)
    monkeypatch.setattr(deps, "supabase_client", client)

    with pytest.raises(VantageError) as exc_info:
        asyncio.run(deps.get_current_user(MagicMock(credentials="valid-token")))

    assert exc_info.value.code == "AUTH_INVALID"


def test_repository_dependency_returns_owner_scoped_repository() -> None:
    assert isinstance(deps.get_research_repository(), ResearchRunRepository)
