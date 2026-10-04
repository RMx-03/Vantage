"""constrain research-run ownership to a real user

Revision ID: 20260920_0004
Revises: 20260920_0003
Create Date: 2026-09-20 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260920_0004"
down_revision: Union[str, None] = "20260920_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Previously, user_id pointed at an external table with no constraint,
    # so orphan rows were possible. Adding the key silently would fail at the
    # worst moment; refuse loudly instead and let an operator decide.
    orphans = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*) FROM vantage_app.research_runs r
            WHERE NOT EXISTS (
                SELECT 1 FROM vantage_auth.users u WHERE u.public_id = r.user_id
            )
            """
            )
        )
        .scalar_one()
    )

    if orphans:
        raise RuntimeError(
            f"{orphans} research_runs rows reference no vantage_auth.users row. "
            "Resolve or delete them before applying this migration."
        )

    op.create_foreign_key(
        "fk_research_runs_user",
        source_table="research_runs",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["public_id"],
        source_schema="vantage_app",
        referent_schema="vantage_auth",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_runs_user",
        "research_runs",
        schema="vantage_app",
        type_="foreignkey",
    )
