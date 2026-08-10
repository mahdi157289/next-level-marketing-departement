"""Add Google Maps lead fields (address, rating, review_count, google_maps_url).

Revision ID: 20260809_0011
Revises: 20260808_0010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0011"
down_revision: Union[str, None] = "20260808_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("address", sa.String(length=512), nullable=True))
    op.add_column("leads", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("review_count", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("google_maps_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "google_maps_url")
    op.drop_column("leads", "review_count")
    op.drop_column("leads", "rating")
    op.drop_column("leads", "address")
