"""agent RAG chunks + vector extension (P3)

Enables pgvector for the Scout/RAG brain. Requires the postgres image to be
pgvector/pgvector:pg16 (the extension is created here via CREATE EXTENSION).

Revision ID: 20260807_0006
Revises: 20260807_0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_0006"
down_revision: Union[str, None] = "20260807_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "agent_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False, server_default="shared"),
        sa.Column("source_uri", sa.String(length=1024), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_index("ix_agent_chunks_agent_scope", "agent_chunks", ["agent_name", "scope"])
    # pgvector column (requires pgvector/pgvector image). HNSW index for cosine.
    op.execute("ALTER TABLE agent_chunks ADD COLUMN embedding vector(768) NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_chunks_embedding_hnsw "
        "ON agent_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_chunks_embedding_hnsw")
    op.drop_index("ix_agent_chunks_agent_scope", table_name="agent_chunks")
    op.drop_table("agent_chunks")
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE")
