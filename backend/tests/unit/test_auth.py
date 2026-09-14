from unittest.mock import MagicMock
import asyncio

import pytest

from app.api import deps
from app.domain.errors import VantageError


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
