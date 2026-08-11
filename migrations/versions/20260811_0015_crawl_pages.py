"""Add crawl_pages cache table.

Revision ID: 20260811_0015
Revises: 20260811_0014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0015"
down_revision: Union[str, None] = "20260811_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512)),
        sa.Column("domain", sa.String(length=256)),
        sa.Column("markdown", sa.Text()),
        sa.Column("fields", sa.JSON()),
        sa.Column("status", sa.String(length=32)),
        sa.Column("source", sa.String(length=32)),
        sa.Column("tags", sa.JSON()),
        sa.Column("fetched_at", sa.TIMESTAMP()),
        sa.UniqueConstraint("url", name="uq_crawl_pages_url"),
    )
    op.create_index("ix_crawl_pages_domain", "crawl_pages", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_crawl_pages_domain", table_name="crawl_pages")
    op.drop_table("crawl_pages")
