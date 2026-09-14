"""create research runs schema and tables

Revision ID: 20260914_0001
Revises: None
Create Date: 2026-09-14 00:00:00.000000+00:00

"""

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260914_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS vantage_app")
    op.execute("REVOKE ALL ON SCHEMA vantage_app FROM PUBLIC")

    op.create_table(
        "research_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "public_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("workflow_status", sa.Text(), nullable=False),
        sa.Column("research_status", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("data_quality", postgresql.JSONB(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("response_schema_version", sa.Text(), nullable=False),
        sa.Column("workflow_version", sa.Text(), nullable=False),
        sa.Column("metrics_version", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message_safe", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "workflow_status IN ('running','succeeded','failed')",
            name="ck_research_runs_workflow_status",
        ),
        sa.CheckConstraint(
            "research_status IS NULL OR research_status IN ('informational','review','insufficient_data','failed')",
            name="ck_research_runs_research_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_research_runs_completed_after_started",
        ),
        schema="vantage_app",
    )
    op.create_index(
        "ix_research_runs_user_created_id",
        "research_runs",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        schema="vantage_app",
    )
    op.create_index(
        "ix_research_runs_user_id",
        "research_runs",
        ["user_id"],
        schema="vantage_app",
    )

    op.create_table(
        "research_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "public_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("vantage_app.research_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("market_provider", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("market_content_hash", sa.Text(), nullable=False),
        sa.Column("news_provider", sa.Text(), nullable=False),
        sa.Column("news_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("news_coverage_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("news_coverage_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("news_quality", sa.Text(), nullable=False),
        sa.Column("news_error_code", sa.Text(), nullable=True),
        sa.Column("price_bars", postgresql.JSONB(), nullable=False),
        sa.Column("quality", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "window_end >= window_start",
            name="ck_research_snapshots_window_order",
        ),
        schema="vantage_app",
    )
    op.create_index(
        "ix_research_snapshots_run_id",
        "research_snapshots",
        ["run_id"],
        schema="vantage_app",
    )
    op.create_index(
        "ix_research_snapshots_user_id",
        "research_snapshots",
        ["user_id"],
        schema="vantage_app",
    )

    op.create_table(
        "research_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("vantage_app.research_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_id", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "snapshot_id",
            "evidence_id",
            name="uq_research_sources_snapshot_evidence",
        ),
        schema="vantage_app",
    )
    op.create_index(
        "ix_research_sources_snapshot_id",
        "research_sources",
        ["snapshot_id"],
        schema="vantage_app",
    )

    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA vantage_app FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA vantage_app FROM PUBLIC")
    runtime_role = os.environ.get("VANTAGE_RUNTIME_DB_ROLE", "").strip()
    if runtime_role:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", runtime_role) is None:
            raise RuntimeError(
                "VANTAGE_RUNTIME_DB_ROLE is not a valid PostgreSQL role name"
            )
        quoted_role = f'"{runtime_role}"'
        op.execute(f"GRANT USAGE ON SCHEMA vantage_app TO {quoted_role}")
        op.execute(
            "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA vantage_app "
            f"TO {quoted_role}"
        )
        op.execute(
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA vantage_app "
            f"TO {quoted_role}"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is disabled because research-run history is immutable; "
        "deploy the prior application version without removing these tables."
    )
