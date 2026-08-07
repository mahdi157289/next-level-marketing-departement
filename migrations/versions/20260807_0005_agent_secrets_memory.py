"""agent secrets + persistent memory (P2)

Adds:
- agent_secrets: per-agent, per-provider encrypted secret store (Fernet tokens).
- agent_memory: per-agent persistent memory / lesson store, scoped for
  domain-partitioned retrieval.

Revision ID: 20260807_0005
Revises: 20260805_0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_0005"
down_revision: Union[str, None] = "20260805_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_secrets",
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("agent_name", "kind"),
    )

    op.create_table(
        "agent_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False, server_default="shared"),
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_index("ix_agent_memory_agent_scope", "agent_memory", ["agent_name", "scope"])


def downgrade() -> None:
    op.drop_index("ix_agent_memory_agent_scope", table_name="agent_memory")
    op.drop_table("agent_memory")
    op.drop_table("agent_secrets")
