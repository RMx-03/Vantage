POSTGRES_SCHEMES = ("postgres://", "postgresql://")
SQLALCHEMY_PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalize_database_url(url: str) -> str:
    """Select the installed psycopg driver for provider-style Postgres URLs."""
    for scheme in POSTGRES_SCHEMES:
        if url.startswith(scheme):
            return SQLALCHEMY_PSYCOPG_SCHEME + url.removeprefix(scheme)
    return url
