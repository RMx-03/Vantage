"""create first-party authentication schema

Revision ID: 20260920_0003
Revises: 20260919_0002
Create Date: 2026-09-20 00:00:00.000000+00:00
"""

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260920_0003"
down_revision: Union[str, None] = "20260919_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "vantage_auth"
_TABLES = ("users", "refresh_tokens", "email_tokens", "auth_attempts")


def _runtime_role() -> str | None:
    role = os.environ.get("VANTAGE_RUNTIME_DB_ROLE", "").strip()
    if not role:
        return None
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role) is None:
        raise RuntimeError(
            "VANTAGE_RUNTIME_DB_ROLE is not a valid PostgreSQL role name"
        )
    return role


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
    op.execute(f"REVOKE ALL ON SCHEMA {_SCHEMA} FROM PUBLIC")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "public_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("password_algo", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','locked','disabled')", name="ck_users_status"
        ),
        schema=_SCHEMA,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("replaced_by_id", sa.BigInteger(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{_SCHEMA}.users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["replaced_by_id"], [f"{_SCHEMA}.refresh_tokens.id"]),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_refresh_tokens_user_expires",
        "refresh_tokens",
        ["user_id", "expires_at"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_refresh_tokens_family", "refresh_tokens", ["family_id"], schema=_SCHEMA
    )

    op.create_table(
        "email_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('email_verification','password_reset')",
            name="ck_email_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{_SCHEMA}.users.id"], ondelete="CASCADE"
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_email_tokens_user_purpose",
        "email_tokens",
        ["user_id", "purpose"],
        schema=_SCHEMA,
    )

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_auth_attempts_key_time",
        "auth_attempts",
        ["key", sa.text("occurred_at DESC")],
        schema=_SCHEMA,
    )

    for table in _TABLES:
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table} FROM PUBLIC")

    role = _runtime_role()
    if role:
        quoted = f'"{role}"'
        op.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO {quoted}")
        for table in _TABLES:
            op.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_SCHEMA}.{table} TO {quoted}"
            )
        op.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {_SCHEMA} TO {quoted}"
        )


def downgrade() -> None:
    """Drop the entire auth schema.

    This destroys every account. It exists so the migration can be exercised
    and reverted against a disposable database; production rollback remains
    forward-fix oriented, as in Phase 1.
    """
    op.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
