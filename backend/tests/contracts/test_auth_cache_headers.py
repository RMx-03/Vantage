"""Every auth response must forbid caching.

Auth responses carry access tokens and the caller's identity, and they reach the
browser through Vercel's edge. A cache that stored one would serve one user's
token or identity to another. The spec requires `Cache-Control: no-store` on
every /auth response, and RFC 6749 section 5.1 requires it on token responses.
Failure responses count too: some are built fresh by exception handlers, which
is why the header cannot be set per route.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _assert_no_store(response) -> None:
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"


def test_a_successful_login_is_not_cacheable(client: TestClient) -> None:
    email = f"cache-{uuid4().hex}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    _assert_no_store(response)


def test_a_rejected_refresh_is_not_cacheable(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    _assert_no_store(response)


def test_an_unauthenticated_me_is_not_cacheable(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    _assert_no_store(response)


def test_logout_is_not_cacheable(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    _assert_no_store(response)


def test_registration_is_not_cacheable(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"cache-{uuid4().hex}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 202
    _assert_no_store(response)
