"""add multi-source snapshot columns and the provider cache

Revision ID: 20261115_0005
Revises: 20260920_0004
Create Date: 2026-11-15 00:00:00.000000+00:00
"""

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20261115_0005"
down_revision: Union[str, None] = "20260920_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "vantage_app"
_SNAPSHOT_COLUMNS = ("providers", "context_bars", "fundamentals", "macro")


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
    # Fail fast instead of queueing behind a long transaction and blocking the
    # tables the running release reads and writes.
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Every added column is nullable, so existing rows and the running release
    # stay valid. Old runs read the new fields back as null.
    for column in _SNAPSHOT_COLUMNS:
        op.add_column(
            "research_snapshots",
            sa.Column(column, postgresql.JSONB(), nullable=True),
            schema=_SCHEMA,
        )
    op.add_column(
        "research_sources",
        sa.Column("summary", sa.Text(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "research_sources",
        sa.Column("details", postgresql.JSONB(), nullable=True),
        schema=_SCHEMA,
    )
    # Every existing row is a news item, so the constraint validates cleanly.
    # The migration runs in one transaction, so the ACCESS EXCLUSIVE lock taken by
    # ADD CONSTRAINT is held until commit, including the VALIDATE scan. That is
    # short at the current table size. lock_timeout makes the release fail fast
    # (retry the release) instead of queueing behind other sessions.
    op.execute(
        "ALTER TABLE vantage_app.research_sources "
        "ADD CONSTRAINT ck_research_sources_source_type "
        "CHECK (source_type IN ('news','filing','insider_transaction')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE vantage_app.research_sources "
        "VALIDATE CONSTRAINT ck_research_sources_source_type"
    )

    op.create_table(
        "provider_cache",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("valid_for_date", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "immutable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.UniqueConstraint(
            "provider",
            "cache_key",
            "valid_for_date",
            name="uq_provider_cache_key",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_provider_cache_retrieved_at",
        "provider_cache",
        ["retrieved_at"],
        schema=_SCHEMA,
    )

    # Only the new table is granted; privileges on existing tables are untouched.
    op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.provider_cache FROM PUBLIC")
    role = _runtime_role()
    if role:
        quoted = f'"{role}"'
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
            f"{_SCHEMA}.provider_cache TO {quoted}"
        )
        op.execute(
            f"GRANT USAGE, SELECT ON SEQUENCE {_SCHEMA}.provider_cache_id_seq "
            f"TO {quoted}"
        )


def downgrade() -> None:
    """Drop the provider cache and the six additive columns.

    Rolling this back discards the cached provider payloads (which are
    re-fetchable) and every stored multi-source field: snapshot providers,
    context bars, fundamentals and macro, plus the summary and details of each
    evidence source. News-only runs lose nothing authoritative. Production
    rollback remains forward-fix oriented; this exists so the additive change
    can be exercised and reverted in a disposable database.
    """
    op.drop_table("provider_cache", schema=_SCHEMA)
    op.drop_constraint(
        "ck_research_sources_source_type",
        "research_sources",
        schema=_SCHEMA,
        type_="check",
    )
    op.drop_column("research_sources", "details", schema=_SCHEMA)
    op.drop_column("research_sources", "summary", schema=_SCHEMA)
    for column in reversed(_SNAPSHOT_COLUMNS):
        op.drop_column("research_snapshots", column, schema=_SCHEMA)
