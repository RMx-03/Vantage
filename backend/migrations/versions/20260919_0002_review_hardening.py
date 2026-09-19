"""add durable model interpretation to research runs

Revision ID: 20260919_0002
Revises: 20260914_0001
Create Date: 2026-09-19 00:00:00.000000+00:00

"""

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260919_0002"
down_revision: Union[str, None] = "20260914_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("interpretation", postgresql.JSONB(), nullable=True),
        schema="vantage_app",
    )

    # Adding a column to an already-granted table preserves the table's existing
    # privileges, so this only reasserts the least-privilege model from
    # 20260914_0001 for the one table touched here. It must not widen it.
    op.execute("REVOKE ALL ON TABLE vantage_app.research_runs FROM PUBLIC")
    runtime_role = os.environ.get("VANTAGE_RUNTIME_DB_ROLE", "").strip()
    if runtime_role:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", runtime_role) is None:
            raise RuntimeError(
                "VANTAGE_RUNTIME_DB_ROLE is not a valid PostgreSQL role name"
            )
        quoted_role = f'"{runtime_role}"'
        op.execute(
            "GRANT SELECT, INSERT, UPDATE ON TABLE vantage_app.research_runs "
            f"TO {quoted_role}"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is disabled because research-run history is immutable; "
        "deploy the prior application version without removing this column."
    )
