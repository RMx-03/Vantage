"""Shared URL safety rules for provider-supplied links.

A source URL crosses two boundaries: the write path, where a provider payload
is normalized before persistence, and the read path, where a stored row is
mapped back into the public model. Both boundaries apply this one allowlist so
they can never diverge -- a row persisted before the write-side guard existed
must not become an href just because it is already in the database.
"""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# A normalized URL is rendered as an href by clients, so only web schemes may
# survive. A payload carrying javascript:, data:, or a scheme-relative
# reference is dropped rather than passed through as a link target.
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def normalize_url(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.netloc:
            return None
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
