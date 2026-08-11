"""Enable web_search + site_extract tools on every agent profile.

Revision ID: 20260811_0016
Revises: 20260811_0015
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0016"
down_revision: Union[str, None] = "20260811_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        for tid in ("web_search", "site_extract"):
            if tid not in tools:
                tools.append(tid)
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )


def downgrade() -> None:
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
        tools = [t for t in (enabled_tools or []) if t not in ("web_search", "site_extract")]
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )