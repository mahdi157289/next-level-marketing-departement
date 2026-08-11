"""Rename hunter tool to research; enable site_extract on discovery.

Revision ID: 20260811_0014
Revises: 20260810_0013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0014"
down_revision: Union[str, None] = "20260810_0013"
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
        tools = [t for t in (enabled_tools or []) if t != "hunter"]
        if "hunter" in (enabled_tools or []) and "research" not in tools:
            tools.append("research")
        if agent_name == "discovery" and "site_extract" not in tools:
            tools.append("site_extract")
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
        tools = [t for t in (enabled_tools or []) if t not in ("research", "site_extract")]
        if "research" in (enabled_tools or []):
            tools.append("hunter")
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )
