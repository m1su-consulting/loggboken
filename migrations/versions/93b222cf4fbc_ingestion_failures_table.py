"""ingestion failures table

Revision ID: 93b222cf4fbc
Revises: 67febf480812
Create Date: 2026-07-07 18:53:29.899139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '93b222cf4fbc'
down_revision: Union[str, Sequence[str], None] = '67febf480812'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingestion_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ingestion_failures_environment_id", "ingestion_failures", ["environment_id"])
    op.create_index("ix_ingestion_failures_created_at", "ingestion_failures", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ingestion_failures_created_at", table_name="ingestion_failures")
    op.drop_index("ix_ingestion_failures_environment_id", table_name="ingestion_failures")
    op.drop_table("ingestion_failures")
