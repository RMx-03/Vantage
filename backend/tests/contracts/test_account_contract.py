from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_forgot_password_returns_202_for_an_unknown_address(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"nobody-{uuid4().hex}@example.com"},
    )
    assert response.status_code == 202


def test_forgot_password_response_is_identical_for_known_and_unknown(
    client: TestClient,
) -> None:
    email = f"fp-{uuid4().hex}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    known = client.post("/api/v1/auth/forgot-password", json={"email": email})
    unknown = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"nobody-{uuid4().hex}@example.com"},
    )
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()


def test_verify_email_with_a_bad_token_is_400(client: TestClient) -> None:
    response = client.post("/api/v1/auth/verify-email", json={"token": "nope"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "AUTH_INVALID"


def test_reset_password_with_a_bad_token_is_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "nope", "password": "a brand new passphrase"},
    )
    assert response.status_code == 400


def test_change_password_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a brand new passphrase"},
    )
    assert response.status_code == 401


def test_change_password_succeeds_and_invalidates_the_session(
    client: TestClient,
) -> None:
    email = f"cp-{uuid4().hex}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a brand new passphrase"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_resend_verification_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_EMAIL_ACTION_MAX_ATTEMPTS", 2)
    email = f"resend-{uuid4().hex}@example.com"
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/resend-verification", json={"email": email}
            ).status_code
            == 202
        )
    assert (
        client.post(
            "/api/v1/auth/resend-verification", json={"email": email}
        ).status_code
        == 429
    )


def test_forgot_password_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_EMAIL_ACTION_MAX_ATTEMPTS", 2)
    email = f"fp-rate-{uuid4().hex}@example.com"
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/forgot-password", json={"email": email}
            ).status_code
            == 202
        )
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": email}).status_code
        == 429
    )


def test_a_failed_reset_leaves_the_session_cookie_alone(client: TestClient) -> None:
    """Nothing was revoked, so there is nothing to clear. Deleting the cookie
    on an expired link or a weak password signed out a valid session."""
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "password": "a brand new passphrase"},
    )
    assert response.status_code == 400
    assert "vantage_refresh=" not in response.headers.get("set-cookie", "")
