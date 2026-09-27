from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _email() -> str:
    return f"api-{uuid4().hex}@example.com"


def test_register_returns_202(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": _email(), "password": PASSWORD})
    assert response.status_code == 202


def test_register_response_is_identical_for_new_and_existing_addresses(
    client: TestClient,
) -> None:
    # The whole point of enumeration resistance. Byte-identical, not merely
    # "both succeed".
    email = _email()
    first = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    second = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert first.status_code == second.status_code
    assert first.json() == second.json()


def test_weak_password_is_rejected_with_the_safe_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": _email(), "password": "short"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "AUTH_WEAK_PASSWORD"
    assert "retryable" in detail


def test_login_sets_an_httponly_refresh_cookie(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert "refresh_token" not in body  # must never reach JavaScript

    raw_cookie = response.headers["set-cookie"]
    assert "vantage_refresh=" in raw_cookie
    assert "HttpOnly" in raw_cookie
    assert "SameSite=Lax" in raw_cookie
    assert "Path=/api/v1/auth" in raw_cookie


def test_logout_clear_matches_the_set_attributes(client: TestClient) -> None:
    # A delete_cookie whose attributes differ from set_cookie is a no-op: the
    # browser keeps the original. Path must match exactly.
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    cleared = client.post("/api/v1/auth/logout").headers["set-cookie"]
    assert "Path=/api/v1/auth" in cleared


def test_refresh_uses_the_cookie_and_rotates_it(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    first_cookie = client.cookies.get("vantage_refresh")

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != login.json()["access_token"]
    assert client.cookies.get("vantage_refresh") != first_cookie


def test_refresh_without_a_cookie_is_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_logout_clears_the_cookie(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert not client.cookies.get("vantage_refresh")


def test_me_requires_a_bearer_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_the_account(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["email_verified"] is False
