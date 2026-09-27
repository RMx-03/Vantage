"""Refresh-token persistence with rotation and reuse detection.

Every refresh consumes one token and issues its successor within a single
transaction. Presenting a token that has already been consumed means either a
replay or a theft, and the only safe response is to revoke the entire rotation
family: the legitimate user re-authenticates, and a stolen token buys nothing.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.core.config import settings
from app.core.security.tokens import hash_opaque_token, mint_opaque_token
from app.db.auth_models import RefreshTokenRow
from app.db.session import SessionFactory

RotationOutcome = Literal["rotated", "not_found", "expired", "reused"]

_MAX_USER_AGENT = 400


@dataclass(frozen=True)
class RotationResult:
    outcome: RotationOutcome
    raw_token: str | None = None
    user_id: int | None = None
    family_id: UUID | None = None


class RefreshTokenRepository:
    def issue(
        self,
        *,
        user_id: int,
        family_id: UUID | None = None,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> tuple[str, UUID]:
        raw, digest = mint_opaque_token()
        family = family_id or uuid4()
        now = datetime.now(UTC)
        row = RefreshTokenRow(
            token_hash=digest,
            user_id=user_id,
            family_id=family,
            issued_at=now,
            expires_at=now + timedelta(seconds=settings.AUTH_REFRESH_TOKEN_TTL_SECONDS),
            user_agent=(user_agent or None) and user_agent[:_MAX_USER_AGENT],
            ip_hash=ip_hash,
        )
        with SessionFactory() as session, session.begin():
            session.add(row)
        return raw, family

    def rotate(
        self,
        raw_token: str,
        *,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> RotationResult:
        digest = hash_opaque_token(raw_token)
        now = datetime.now(UTC)

        with SessionFactory() as session, session.begin():
            row = session.execute(
                select(RefreshTokenRow)
                .where(RefreshTokenRow.token_hash == digest)
                .with_for_update()
            ).scalar_one_or_none()

            if row is None:
                return RotationResult(outcome="not_found")

            if row.revoked_at is not None:
                # Already consumed or revoked. Treat as theft and burn the family.
                self._revoke_family_in_session(session, row.family_id, now, "reuse_detected")
                return RotationResult(outcome="reused", family_id=row.family_id)

            if row.expires_at <= now:
                row.revoked_at = now
                row.revoked_reason = "expired"
                return RotationResult(outcome="expired")

            successor_raw, successor_digest = mint_opaque_token()
            successor = RefreshTokenRow(
                token_hash=successor_digest,
                user_id=row.user_id,
                family_id=row.family_id,
                issued_at=now,
                expires_at=now
                + timedelta(seconds=settings.AUTH_REFRESH_TOKEN_TTL_SECONDS),
                user_agent=(user_agent or None) and user_agent[:_MAX_USER_AGENT],
                ip_hash=ip_hash,
            )
            session.add(successor)
            session.flush()

            row.revoked_at = now
            row.revoked_reason = "rotated"
            row.replaced_by_id = successor.id

            return RotationResult(
                outcome="rotated",
                raw_token=successor_raw,
                user_id=row.user_id,
                family_id=row.family_id,
            )

    def revoke(self, raw_token: str, *, reason: str) -> None:
        digest = hash_opaque_token(raw_token)
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            session.execute(
                update(RefreshTokenRow)
                .where(
                    RefreshTokenRow.token_hash == digest,
                    RefreshTokenRow.revoked_at.is_(None),
                )
                .values(revoked_at=now, revoked_reason=reason)
            )

    def revoke_all_for_user(self, user_id: int, *, reason: str) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            session.execute(
                update(RefreshTokenRow)
                .where(
                    RefreshTokenRow.user_id == user_id,
                    RefreshTokenRow.revoked_at.is_(None),
                )
                .values(revoked_at=now, revoked_reason=reason)
            )

    @staticmethod
    def _revoke_family_in_session(
        session: object, family_id: UUID, now: datetime, reason: str
    ) -> None:
        session.execute(  # type: ignore[attr-defined]
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.family_id == family_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason=reason)
        )
