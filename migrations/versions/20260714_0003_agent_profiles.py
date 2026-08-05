"""agent profiles + cancelled run status

Revision ID: 20260714_0003
Revises: 20260711_0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0003"
down_revision: Union[str, None] = "20260711_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DISCOVERY_MISSION = (
    "You are the Discovery Agent for a Tunisia-based tech agency pipeline. "
    "Given web search hits (JSON with title, url, snippet), propose up to 5 plausible prospects: "
    "company/site name, primary URL, one-line fit, confidence low/med/high. "
    "Respond as Markdown bullets only."
)

HEAD_MISSION = (
    "You are the Head Agent: prioritize execution for the marketing department. "
    "Given the Discovery Agent markdown and how many raw hits were retrieved, "
    "output: (1) top 3 priorities, (2) risks/blockers, (3) next concrete actions — "
    "max 12 lines, terse Markdown."
)


def upgrade() -> None:
    op.execute("ALTER TYPE runstatus ADD VALUE IF NOT EXISTS 'cancelled'")

    op.create_table(
        "agent_profiles",
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("mission_prompt", sa.Text(), nullable=False),
        sa.Column("enabled_tools", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("default_seed_query", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("agent_name"),
    )

    agent_profiles = sa.table(
        "agent_profiles",
        sa.column("agent_name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("mission_prompt", sa.Text),
        sa.column("enabled_tools", postgresql.JSON),
        sa.column("model", sa.String),
        sa.column("default_seed_query", sa.Text),
        sa.column("updated_at", sa.TIMESTAMP),
    )
    op.bulk_insert(
        agent_profiles,
        [
            {
                "agent_name": "discovery",
                "display_name": "Discovery (Scout)",
                "mission_prompt": DISCOVERY_MISSION,
                "enabled_tools": ["web_search", "crm_write_leads", "llm_chat"],
                "model": None,
                "default_seed_query": "digital marketing agencies Tunisia",
                "updated_at": None,
            },
            {
                "agent_name": "head",
                "display_name": "Head (Supervisor)",
                "mission_prompt": HEAD_MISSION,
                "enabled_tools": ["llm_chat"],
                "model": None,
                "default_seed_query": None,
                "updated_at": None,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("agent_profiles")
    # PostgreSQL cannot easily remove enum values; leave cancelled in place.
