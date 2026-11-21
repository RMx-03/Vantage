"""store the price cross-check closes on the research snapshot

Revision ID: 20261122_0006
Revises: 20261115_0005
Create Date: 2026-11-22 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20261122_0006"
down_revision: Union[str, None] = "20261115_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "vantage_app"


def upgrade() -> None:
    # Fail fast instead of queueing behind a long transaction.
    op.execute("SET LOCAL lock_timeout = '5s'")
    # Nullable, so existing rows and the running release stay valid. Old runs
    # read the cross-check back as null. No grant is needed: the runtime role
    # already holds table-level privileges on research_snapshots.
    op.add_column(
        "research_snapshots",
        sa.Column("crosscheck", postgresql.JSONB(), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    """Drop the cross-check column, discarding the stored closes of new runs."""
    op.drop_column("research_snapshots", "crosscheck", schema=_SCHEMA)
