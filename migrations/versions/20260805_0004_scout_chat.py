"""scout chat tables

Revision ID: 20260805_0004
Revises: 20260714_0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0004"
down_revision: Union[str, None] = "20260714_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_table(
        "scout_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("tool_args", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_index("ix_scout_messages_thread_id", "scout_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_scout_messages_thread_id", table_name="scout_messages")
    op.drop_table("scout_messages")
    op.drop_table("scout_threads")
