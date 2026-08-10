"""Add Lead completion fields (hours, description, price_level, socials, tags).

Revision ID: 20260810_0012
Revises: 20260809_0011
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0012"
down_revision: Union[str, None] = "20260809_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("hours", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("price_level", sa.String(length=16), nullable=True))
    op.add_column("leads", sa.Column("facebook", sa.String(length=512), nullable=True))
    op.add_column("leads", sa.Column("instagram", sa.String(length=512), nullable=True))
    op.add_column("leads", sa.Column("linkedin", sa.String(length=512), nullable=True))
    op.add_column("leads", sa.Column("twitter", sa.String(length=512), nullable=True))
    op.add_column("leads", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "tags")
    op.drop_column("leads", "twitter")
    op.drop_column("leads", "linkedin")
    op.drop_column("leads", "instagram")
    op.drop_column("leads", "facebook")
    op.drop_column("leads", "price_level")
    op.drop_column("leads", "description")
    op.drop_column("leads", "hours")
