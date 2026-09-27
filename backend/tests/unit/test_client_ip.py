"""Deriving the real client address behind Vercel and Heroku's router.

Behind proxies, request.client.host is the proxy. Rate limits keyed on it
collapse every user into one bucket: login throttling degrades to per-email
(re-opening the lockout attack) and registration becomes a global cap.
"""

import pytest
from starlette.requests import Request

from app.api.client_ip import client_ip
from app.core.config import settings


def _request(peer: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers,
            "client": (peer, 1234),
        }
    )


def test_without_trusted_proxies_the_socket_peer_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Locally nothing sits in front of the app, so the header is untrusted and
    # must be ignored: anyone could set it.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    assert client_ip(_request("10.0.0.1", "203.0.113.9")) == "10.0.0.1"


def test_behind_vercel_and_heroku_the_client_is_second_from_the_right(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Vercel overwrites X-Forwarded-For with the real client, then Heroku's
    # router appends the Vercel edge it received the connection from.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    request = _request("10.1.2.3", "198.51.100.7, 76.76.21.21")
    assert client_ip(request) == "198.51.100.7"


def test_behind_heroku_alone_the_rightmost_entry_is_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Anything left of the router's own entry was supplied by the caller.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    request = _request("10.1.2.3", "1.2.3.4, 198.51.100.7")
    assert client_ip(request) == "198.51.100.7"


def test_fewer_entries_than_hops_uses_the_earliest_known_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A request reaching Heroku directly has passed one proxy, not two.
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client_ip(_request("10.1.2.3", "198.51.100.7")) == "198.51.100.7"


def test_a_malformed_entry_falls_back_to_the_socket_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client_ip(_request("10.1.2.3", "not-an-ip, 76.76.21.21")) == "10.1.2.3"


def test_a_missing_header_falls_back_to_the_socket_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client_ip(_request("10.1.2.3")) == "10.1.2.3"
