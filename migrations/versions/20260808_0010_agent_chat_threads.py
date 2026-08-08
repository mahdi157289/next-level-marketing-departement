"""Add agent_name to scout_threads / scout_messages (agent chat generalization).

Revision ID: 20260808_0010
Revises: 20260808_0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0010"
down_revision: Union[str, None] = "20260808_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scout_threads",
        sa.Column("agent_name", sa.String(length=32), nullable=False, server_default="discovery"),
    )
    op.add_column(
        "scout_messages",
        sa.Column("agent_name", sa.String(length=32), nullable=False, server_default="discovery"),
    )
    op.create_index("ix_scout_threads_agent_name", "scout_threads", ["agent_name"])
    op.create_index("ix_scout_messages_agent_name", "scout_messages", ["agent_name"])


def downgrade() -> None:
    op.drop_index("ix_scout_messages_agent_name", table_name="scout_messages")
    op.drop_index("ix_scout_threads_agent_name", table_name="scout_threads")
    op.drop_column("scout_messages", "agent_name")
    op.drop_column("scout_threads", "agent_name")
