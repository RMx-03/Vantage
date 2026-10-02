from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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

    query_params = parse_qsl(parts.query, keep_blank_values=True)
    query_keys = {k for k, _ in query_params}

    if hostname and hostname not in LOCAL_HOSTS and "sslmode" not in query_keys:
        query_params.append(("sslmode", "require"))

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query_params),
            parts.fragment,
        )
    )
