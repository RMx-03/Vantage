"""The suite must refuse to write anywhere but the test database.

Integration tests create users and research runs and never remove them. Pointed
at the Docker dev database, or at production through a stray DATABASE_URL, they
would fill it with fixture rows. The old guard lived in one module and checked
the environment variable rather than the URL the application actually resolves.
"""

import pytest

from tests.db_guard import require_test_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://runtime:pw@localhost:5433/vantage_test",
        "postgresql+psycopg://runtime:pw@localhost:5432/vantage_test",
    ],
)
def test_the_test_database_is_accepted(url: str) -> None:
    require_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://runtime:pw@localhost:5433/vantage",
        "postgresql+psycopg://u:pw@ec2-1-2-3-4.compute-1.amazonaws.com:5432/d8abc123",
        "postgresql+psycopg://runtime:pw@localhost:5433/vantage_test_copy",
        "",
    ],
)
def test_any_other_database_is_refused(url: str) -> None:
    with pytest.raises(RuntimeError, match="vantage_test"):
        require_test_database(url)


def test_the_resolved_url_is_the_test_database() -> None:
    """Checks what the app will actually connect to, not an env var."""
    from app.db.session import get_database_url

    require_test_database(get_database_url())
