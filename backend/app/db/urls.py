from urllib.parse import parse_qsl, urlsplit

LOCAL_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "postgres", "db", "host.docker.internal"}
)
POSTGRES_SCHEMES = ("postgres://", "postgresql://")
SQLALCHEMY_PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalize_database_url(url: str) -> str:
    """Select psycopg driver for Postgres URLs and require TLS for remote hosts."""
    if not url or not url.strip():
        raise ValueError("A database URL is required.")

    parts = urlsplit(url)
    if not parts.scheme.startswith("postgres"):
        return url

    normalized_url = url
    for scheme in POSTGRES_SCHEMES:
        if normalized_url.startswith(scheme):
            normalized_url = SQLALCHEMY_PSYCOPG_SCHEME + normalized_url.removeprefix(
                scheme
            )
            break

    parts = urlsplit(normalized_url)
    hostname = (parts.hostname or "").lower()
    query_keys = {k for k, _ in parse_qsl(parts.query, keep_blank_values=True)}

    if not hostname or hostname in LOCAL_HOSTS or "sslmode" in query_keys:
        return normalized_url

    # Append rather than rebuild. urlunsplit drops the "//" of an empty-host
    # socket URL, and urlencode rewrites existing query values; neither is
    # ours to change.
    base, hash_mark, fragment = normalized_url.partition("#")
    separator = "" if base.endswith(("?", "&")) else ("&" if parts.query else "?")
    return base + separator + "sslmode=require" + hash_mark + fragment
