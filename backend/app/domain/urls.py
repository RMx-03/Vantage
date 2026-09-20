"""Shared URL safety rules for provider-supplied links.

A source URL crosses two boundaries. On the write path a provider payload is
rejected and then canonicalized before persistence. On the read path a stored
row is mapped back into the public model, where the same rejection must apply
-- a row persisted before the write-side guard existed must not become an href
just because it is already in the database.

Both boundaries reject through the one allowlist in `has_allowed_url_scheme`,
so they cannot drift apart. They deliberately differ in what they do with a URL
that passes: the write path canonicalizes, while the read path returns the
stored value byte for byte. A published payload has to be able to reproduce its
own `content_hash`, which was computed over the stored URL, so rewriting a
safe-but-unnormalized legacy value on the way out would break the branch's
reconstructable-provenance promise for exactly those rows.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# A URL is rendered as an href by clients, so only web schemes may survive. A
# value carrying javascript:, data:, or a scheme-relative reference is dropped
# rather than passed through as a link target.
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def has_allowed_url_scheme(url: str | None) -> bool:
    """The single allowlist: a web scheme and a host, or it is not a link."""
    if not url or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    return parsed.scheme.lower() in ALLOWED_URL_SCHEMES and bool(parsed.netloc)


def normalize_url(url: str | None) -> str | None:
    """Write path: reject, then canonicalize before the value is persisted."""
    if url is None or not has_allowed_url_scheme(url):
        return None
    try:
        parsed = urlparse(url.strip())
        clean_netloc = parsed.netloc.lower()
        clean_scheme = parsed.scheme.lower()
        clean_path = parsed.path.rstrip("/")
        # Filter out tracking query params like utm_*
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if not k.lower().startswith("utm_")
        ]
        clean_query = urlencode(sorted(query_pairs))
        return urlunparse((clean_scheme, clean_netloc, clean_path, "", clean_query, ""))
    except Exception:
        return None


def safe_stored_url(url: str | None) -> str | None:
    """Read path: reject only.

    An accepted value is returned exactly as stored, because the run's
    published `content_hash` was derived from those bytes and the run itself is
    immutable. A rejected value becomes None, matching the write path and the
    already-nullable `EvidenceSource.url`.
    """
    if url is None or not has_allowed_url_scheme(url):
        return None
    return url
