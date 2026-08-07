"""Add brain_query_metrics table (P4 — RAG query telemetry)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260807_0007"
down_revision = "20260807_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brain_query_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("query_hash", sa.String(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vector_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("graph_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_brain_query_metrics_agent_created", "brain_query_metrics", ["agent_name", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_brain_query_metrics_agent_created", table_name="brain_query_metrics")
    op.drop_table("brain_query_metrics")
