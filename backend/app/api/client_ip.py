"""The real client address when the app sits behind proxies.

In production a request travels client -> Vercel edge -> Heroku router -> dyno,
so request.client is the router. Rate limits keyed on it would put every user
in one bucket.

X-Forwarded-For is trusted only as far as TRUSTED_PROXY_HOPS says. Each trusted
proxy contributes the rightmost entries; the client is the entry just left of
them. Entries further left were supplied by the caller and are ignored. A caller
reaching Heroku directly can still choose that entry, which is why protections
that must hold regardless (per-account lockout, the Argon2 concurrency cap) do
not depend on the client address.
"""

import ipaddress

from starlette.requests import Request

from app.core.config import settings


def _valid(address: str) -> str | None:
    try:
        return str(ipaddress.ip_address(address.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str | None:
    peer = request.client.host if request.client else None
    hops = settings.TRUSTED_PROXY_HOPS
    if hops <= 0:
        return peer

    header = request.headers.get("x-forwarded-for", "")
    entries = [entry.strip() for entry in header.split(",") if entry.strip()]
    if not entries:
        return peer

    # Fewer entries than hops means fewer proxies were traversed (a direct hit
    # on Heroku); the earliest recorded address is then the best available.
    chosen = entries[-hops] if len(entries) >= hops else entries[0]
    return _valid(chosen) or peer
