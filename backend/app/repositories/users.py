from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.auth_models import UserRow
from app.db.session import SessionFactory


@dataclass(frozen=True)
class StoredUser:
    id: int
    public_id: UUID
    email: str
    password_hash: str
    password_algo: str
    email_verified: bool
    status: str
    locked_until: datetime | None


def _to_stored(row: UserRow) -> StoredUser:
    return StoredUser(
        id=row.id,
        public_id=row.public_id,
        email=row.email,
        password_hash=row.password_hash,
        password_algo=row.password_algo,
        email_verified=row.email_verified_at is not None,
        status=row.status,
        locked_until=row.locked_until,
    )


class UserRepository:
    def create(
        self, *, email: str, password_hash: str, password_algo: str
    ) -> StoredUser:
        now = datetime.now(UTC)
        row = UserRow(
            public_id=uuid4(),
            email=email,
            password_hash=password_hash,
            password_algo=password_algo,
            status="active",
            failed_login_count=0,
            created_at=now,
            updated_at=now,
        )
        with SessionFactory() as session, session.begin():
            session.add(row)
            session.flush()
            return _to_stored(row)

    def find_by_email(self, email: str) -> StoredUser | None:
        with SessionFactory() as session:
            row = session.execute(
                select(UserRow).where(UserRow.email == email)
            ).scalar_one_or_none()
            return _to_stored(row) if row else None

    def find_by_public_id(self, public_id: UUID) -> StoredUser | None:
        with SessionFactory() as session:
            row = session.execute(
                select(UserRow).where(UserRow.public_id == public_id)
            ).scalar_one_or_none()
            return _to_stored(row) if row else None

    def record_successful_login(self, user_id: int) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = session.get(UserRow, user_id)
            if row is None:
                return
            row.failed_login_count = 0
            row.locked_until = None
            row.last_login_at = now
            row.updated_at = now

    def record_failed_login(
        self, user_id: int, *, lock_after: int, lock_for_seconds: int
    ) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = session.get(UserRow, user_id)
            if row is None:
                return
            row.failed_login_count += 1
            if row.failed_login_count >= lock_after:
                row.locked_until = now + timedelta(seconds=lock_for_seconds)
            row.updated_at = now

    def update_password(
        self, user_id: int, *, password_hash: str, password_algo: str
    ) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = session.get(UserRow, user_id)
            if row is None:
                return
            row.password_hash = password_hash
            row.password_algo = password_algo
            # A successful password change clears a lockout: the legitimate
            # owner has demonstrated control of the account.
            row.failed_login_count = 0
            row.locked_until = None
            row.updated_at = now

    def mark_email_verified(self, user_id: int) -> None:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = session.get(UserRow, user_id)
            if row is None:
                return
            if row.email_verified_at is None:
                row.email_verified_at = now
            row.updated_at = now
