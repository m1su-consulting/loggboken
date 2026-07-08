"""environment uniqueness and snapshot lock

Revision ID: 67febf480812
Revises: 6a87e6013330
Create Date: 2026-07-07 18:37:11.749003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67febf480812'
down_revision: Union[str, Sequence[str], None] = '6a87e6013330'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # (name, source_type) is the practical identity of an environment; without
    # this constraint, environment upsert can only be select-then-insert,
    # which races under concurrent requests for a brand new environment.
    op.create_unique_constraint(
        "uq_environments_name_source_type", "environments", ["name", "source_type"]
    )

    # simple per-environment guard so two concurrent snapshot requests for the
    # same environment can't interleave their diff logic against each other.
    op.add_column(
        "environments",
        sa.Column(
            "snapshot_in_progress", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("environments", "snapshot_in_progress")
    op.drop_constraint("uq_environments_name_source_type", "environments", type_="unique")
