"""add the Research Workbench experiments table

Revision ID: 20261122_0007
Revises: 20261122_0006
Create Date: 2026-11-22 00:00:00.000000+00:00
"""

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20261122_0007"
down_revision: Union[str, None] = "20261122_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "vantage_app"


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
    # Additive only: a new table, so the running release is unaffected.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("research_status", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message_safe", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.BYTEA(), nullable=True),
        sa.Column("inputs_hash", sa.Text(), nullable=True),
        sa.Column(
            "inputs_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("versions", postgresql.JSONB(), nullable=False),
        sa.Column("replay_of", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("public_id", name="experiments_public_id_key"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["vantage_auth.users.public_id"],
            name="experiments_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replay_of"],
            [f"{_SCHEMA}.experiments.public_id"],
            name="experiments_replay_of_fkey",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed')", name="ck_experiments_status"
        ),
        sa.CheckConstraint(
            "research_status IS NULL OR research_status IN "
            "('informational','review','insufficient_data','failed')",
            name="ck_experiments_research_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_experiments_completed_after_started",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_experiments_user_created_id",
        "experiments",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_experiments_running_started",
        "experiments",
        ["started_at"],
        schema=_SCHEMA,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.experiments FROM PUBLIC")
    role = _runtime_role()
    if role:
        quoted = f'"{role}"'
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_SCHEMA}.experiments "
            f"TO {quoted}"
        )
        op.execute(
            f"GRANT USAGE, SELECT ON SEQUENCE {_SCHEMA}.experiments_id_seq TO {quoted}"
        )


def downgrade() -> None:
    """Drop the experiments table, discarding every saved simulation.

    Never run this against production: experiments are not re-fetchable, and
    release rollbacks after 20260920_0004 are fix-forward only.
    """
    op.drop_table("experiments", schema=_SCHEMA)
