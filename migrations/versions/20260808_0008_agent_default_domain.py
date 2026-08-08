"""Add agent_profiles.default_domain (P6 — brain scoping)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_0008"
down_revision = "20260807_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("default_domain", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_profiles", "default_domain")
