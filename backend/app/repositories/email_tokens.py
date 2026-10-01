from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.security.tokens import hash_opaque_token, mint_opaque_token
from app.db.auth_models import EmailTokenRow
from app.db.session import SessionFactory


@dataclass(frozen=True)
class ConsumedToken:
    user_id: int
    email: str


class EmailTokenRepository:
    def issue(self, *, user_id: int, purpose: str, email: str, ttl_seconds: int) -> str:
        raw, digest = mint_opaque_token()
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            session.add(
                EmailTokenRow(
                    token_hash=digest,
                    user_id=user_id,
                    purpose=purpose,
                    email=email,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                    created_at=now,
                )
            )
        return raw

    def peek(self, raw_token: str, *, purpose: str) -> ConsumedToken | None:
        """Return what a token would yield, without spending it.

        Lets a caller validate input against the token (a new password against
        the address it was sent to) before committing the single use. Same
        failure semantics as consume: every invalid case is None.
        """
        digest = hash_opaque_token(raw_token)
        now = datetime.now(UTC)
        with SessionFactory() as session:
            row = session.execute(
                select(EmailTokenRow).where(EmailTokenRow.token_hash == digest)
            ).scalar_one_or_none()
            if row is None or row.purpose != purpose:
                return None
            if row.consumed_at is not None or row.expires_at <= now:
                return None
            return ConsumedToken(user_id=row.user_id, email=row.email)

    def consume(self, raw_token: str, *, purpose: str) -> ConsumedToken | None:
        """Atomically spend a token. Returns None for every failure mode.

        Unknown, expired, already-used, and wrong-purpose are deliberately
        indistinguishable to the caller: distinguishing them tells someone
        holding a guessed token which guess was closer.
        """
        digest = hash_opaque_token(raw_token)
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = session.execute(
                select(EmailTokenRow)
                .where(EmailTokenRow.token_hash == digest)
                .with_for_update()
            ).scalar_one_or_none()

            if row is None or row.purpose != purpose:
                return None
            if row.consumed_at is not None or row.expires_at <= now:
                return None

            row.consumed_at = now
            return ConsumedToken(user_id=row.user_id, email=row.email)

    def invalidate_outstanding(self, user_id: int, *, purpose: str) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            session.execute(
                update(EmailTokenRow)
                .where(
                    EmailTokenRow.user_id == user_id,
                    EmailTokenRow.purpose == purpose,
                    EmailTokenRow.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
