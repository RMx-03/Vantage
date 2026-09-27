"""Sliding-window rate limiting backed by PostgreSQL.

Redis is the conventional store for this, but Heroku Key-Value Store Mini costs
$3/month against a $13/month credit already spent on a dyno and Postgres. At
the volumes a single-dyno research tool sees, an indexed count over a short
window is inexpensive.

Keys never contain a raw email address or IP. The table would otherwise become
a record of who attempted to sign in and from where.
"""

from datetime import UTC, datetime, timedelta
import hashlib

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.auth_models import AuthAttemptRow
from app.db.session import SessionFactory


def attempt_key(kind: str, value: str) -> str:
    """Build a rate-limit key from a kind and a sensitive value."""
    salted = f"{settings.TELEMETRY_USER_SALT}:{value.strip().lower()}"
    digest = hashlib.sha256(salted.encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


class AuthAttemptRepository:
    def record(self, key: str) -> None:
        with SessionFactory() as session, session.begin():
            session.add(AuthAttemptRow(key=key, occurred_at=datetime.now(UTC)))

    def count_within(self, key: str, *, window_seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        with SessionFactory() as session:
            return int(
                session.execute(
                    select(func.count())
                    .select_from(AuthAttemptRow)
                    .where(
                        AuthAttemptRow.key == key, AuthAttemptRow.occurred_at > cutoff
                    )
                ).scalar_one()
            )

    def is_rate_limited(
        self, key: str, *, window_seconds: int, max_attempts: int
    ) -> bool:
        return self.count_within(key, window_seconds=window_seconds) >= max_attempts

    def clear(self, key: str) -> None:
        """Drop every attempt for one key.

        Called after a successful login so earlier failures cannot keep
        throttling the person who has just proved they own the account.
        """
        with SessionFactory() as session, session.begin():
            session.execute(delete(AuthAttemptRow).where(AuthAttemptRow.key == key))

    def purge_older_than(self, seconds: int) -> int:
        """Delete attempts outside the retention window. Returns rows removed."""
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        with SessionFactory() as session, session.begin():
            result = session.execute(
                delete(AuthAttemptRow).where(AuthAttemptRow.occurred_at <= cutoff)
            )
            return int(getattr(result, "rowcount", 0) or 0)
