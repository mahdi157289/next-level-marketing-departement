"""Add leads.research + enable hunter tool on all profiles.

Revision ID: 20260810_0013
Revises: 20260810_0012
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0013"
down_revision: Union[str, None] = "20260810_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("research", sa.JSON(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT agent_name, enabled_tools FROM agent_profiles WHERE enabled_tools IS NOT NULL"
    )).fetchall()
    profiles = sa.table(
        "agent_profiles",
        sa.column("agent_name", sa.String),
        sa.column("enabled_tools", postgresql.JSON),
    )
    for agent_name, enabled_tools in rows:
        tools = list(enabled_tools or [])
        if "hunter" not in tools:
            tools.append("hunter")
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )


def downgrade() -> None:
    op.drop_column("leads", "research")
