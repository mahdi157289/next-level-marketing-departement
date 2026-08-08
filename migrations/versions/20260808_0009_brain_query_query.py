"""Add brain_query_metrics.query (P6 — show what the agent asked for)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_0009"
down_revision = "20260808_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brain_query_metrics", sa.Column("query", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("brain_query_metrics", "query")
