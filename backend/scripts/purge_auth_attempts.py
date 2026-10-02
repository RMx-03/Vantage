"""Delete rate-limit attempts that no live window can still read.

Writes already reclaim their own key's expired rows. This sweep covers keys
that are never written again — a one-off source probing once and leaving —
which would otherwise remain forever. Intended for a daily Heroku Scheduler job,
run from the backend root as a module:

    python -m scripts.purge_auth_attempts

Invoking the file directly puts scripts/ rather than the backend root on the
import path, and fails with ModuleNotFoundError: No module named 'app'.
"""

import logging

from app.repositories.auth_attempts import AuthAttemptRepository, retention_seconds

logger = logging.getLogger(__name__)


def sweep() -> int:
    """Remove every attempt older than the longest rate-limit window."""
    removed = AuthAttemptRepository().purge_older_than(retention_seconds())
    logger.info("auth_attempts.purged count=%s", removed)
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sweep()
