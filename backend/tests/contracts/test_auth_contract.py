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
    response = client.post(
        "/api/v1/auth/register", json={"email": _email(), "password": PASSWORD}
    )
    assert response.status_code == 202


def test_register_response_is_identical_for_new_and_existing_addresses(
    client: TestClient,
) -> None:
    # The whole point of enumeration resistance. Byte-identical, not merely
    # "both succeed".
    email = _email()
    first = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    second = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert first.status_code == second.status_code
    assert first.json() == second.json()


def test_weak_password_is_rejected_with_the_safe_error_envelope(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": _email(), "password": "short"}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "AUTH_WEAK_PASSWORD"
    assert "retryable" in detail


def test_login_sets_an_httponly_refresh_cookie(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
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
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
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
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["email_verified"] is False


def test_a_rejected_refresh_cookie_is_cleared(client: TestClient) -> None:
    """A dead refresh cookie must be deleted on the way out.

    The route cleared the cookie on the injected Response and then re-raised,
    but the VantageError handler builds a fresh JSONResponse, discarding those
    headers. The browser kept the dead cookie and retried it on every load.
    """
    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": "vantage_refresh=not-a-real-token"},
    )

    assert response.status_code == 401
    set_cookie = response.headers.get("set-cookie", "")
    assert "vantage_refresh=" in set_cookie, "no Set-Cookie clearing the dead cookie"
    assert "Max-Age=0" in set_cookie or "expires=Thu, 01 Jan 1970" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie


def _signed_in(client: TestClient) -> None:
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def test_a_cross_site_refresh_is_rejected_and_leaves_the_cookie(
    client: TestClient,
) -> None:
    """Cookie-authenticated endpoints must not act on cross-site requests.

    SameSite=Lax is the only thing stopping a forged refresh today, and the
    cookie's SameSite is configurable. Rejecting on Sec-Fetch-Site holds whatever
    it is set to. The rejection must not clear the cookie, or a forged request
    becomes a way to sign the victim out.
    """
    _signed_in(client)

    response = client.post(
        "/api/v1/auth/refresh", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403
    assert "vantage_refresh=" not in response.headers.get("set-cookie", "")
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_a_cross_site_logout_is_rejected(client: TestClient) -> None:
    _signed_in(client)

    response = client.post(
        "/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_same_origin_refresh_is_allowed(client: TestClient) -> None:
    _signed_in(client)
    response = client.post(
        "/api/v1/auth/refresh", headers={"Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code == 200


def test_users_behind_the_same_proxy_get_separate_rate_limits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behind Vercel and Heroku every request arrives from the proxy.

    Keyed on the socket address, twenty sign-ups from anyone would lock out
    every other new user for an hour. The limit must follow the real client.
    """
    from uuid import uuid4 as _uuid4

    from app.core.config import settings

    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 2)
    busy = f"198.51.100.{_uuid4().int % 250 + 1}"
    other = f"203.0.113.{_uuid4().int % 250 + 1}"

    def register(ip: str) -> int:
        return client.post(
            "/api/v1/auth/register",
            json={"email": _email(), "password": PASSWORD},
            headers={"X-Forwarded-For": f"{ip}, 76.76.21.21"},
        ).status_code

    for _ in range(2):
        register(busy)
    assert register(busy) == 429
    assert register(other) == 202
