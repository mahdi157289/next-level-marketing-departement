"""initial_schema

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260507_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

leadstatus = postgresql.ENUM(
    "raw",
    "categorized",
    "enriched",
    "contacted",
    "converted",
    "unreachable",
    "low_priority",
    name="leadstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    leadstatus.create(bind, checkfirst=True)

    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("business_type", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("seo_score", sa.Integer(), nullable=True),
        sa.Column("automation_gaps", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("social_engagement", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("lead_score", sa.Float(), nullable=True),
        sa.Column("status", leadstatus, nullable=True),
        sa.Column("status_notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )

    op.create_table(
        "outreach_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("to_address", sa.String(length=256), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("opened", sa.Boolean(), nullable=True),
        sa.Column("replied", sa.Boolean(), nullable=True),
        sa.Column("converted", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "company_knowledge",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "campaign_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.TIMESTAMP(), nullable=True),
        sa.Column("open_rate", sa.Float(), nullable=True),
        sa.Column("reply_rate", sa.Float(), nullable=True),
        sa.Column("conversion_rate", sa.Float(), nullable=True),
        sa.Column("top_segment", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("strategy_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "task_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("records_processed", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("task_log")
    op.drop_table("campaign_metrics")
    op.drop_table("company_knowledge")
    op.drop_table("outreach_records")
    op.drop_table("leads")
    leadstatus.drop(op.get_bind(), checkfirst=True)
