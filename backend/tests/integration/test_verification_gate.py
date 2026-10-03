from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.users import UserRepository
from app.services.auth import AuthService

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _account(verified: bool) -> str:
    email = f"gate-{uuid4().hex}@example.com"
    auth = AuthService()
    auth.register(email=email, password=PASSWORD)
    if verified:
        stored = UserRepository().find_by_email(email)
        assert stored is not None
        UserRepository().mark_email_verified(stored.id)
    return auth.login(email=email, password=PASSWORD).access_token


def test_unverified_account_cannot_start_a_run(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={"Authorization": f"Bearer {_account(verified=False)}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_EMAIL_UNVERIFIED"


def test_verified_account_is_not_blocked_by_the_gate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={"Authorization": f"Bearer {_account(verified=True)}"},
    )
    assert response.status_code != 403


def test_unverified_account_can_still_read_its_own_account(client: TestClient) -> None:
    # The gate blocks doing work, not seeing who you are. Otherwise the UI
    # cannot render a "verify your address" prompt.
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {_account(verified=False)}"},
    )
    assert response.status_code == 200


def test_unverified_account_can_list_history(client: TestClient) -> None:
    response = client.get(
        "/api/v1/research-runs",
        headers={"Authorization": f"Bearer {_account(verified=False)}"},
    )
    assert response.status_code == 200
