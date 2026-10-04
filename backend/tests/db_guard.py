"""Refuse to run the suite against anything but the test database."""

from urllib.parse import urlsplit

TEST_DATABASE = "vantage_test"


def require_test_database(url: str) -> None:
    """Raise unless `url` names the test database exactly.

    Integration tests create users and research runs and never remove them, so
    any other target would be filled with fixture rows. An exact match matters:
    a substring check would accept `vantage_test_copy` or a production name
    that merely contains the word.
    """
    name = urlsplit(url).path.lstrip("/") if url else ""
    if name != TEST_DATABASE:
        raise RuntimeError(
            f"Tests must run against the '{TEST_DATABASE}' database; "
            f"the resolved DATABASE_URL targets '{name or '<none>'}'."
        )
