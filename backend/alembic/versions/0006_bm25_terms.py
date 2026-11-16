"""bm25 chunk terms

Revision ID: 0006_bm25_terms
Revises: 0005_document_sources
Create Date: 2026-11-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_bm25_terms"
down_revision: str | None = "0005_document_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "chunk_terms",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("tf", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id", "term"),
    )
    op.create_index("ix_chunk_terms_term", "chunk_terms", ["term"])


def downgrade() -> None:
    op.drop_index("ix_chunk_terms_term", table_name="chunk_terms")
    op.drop_table("chunk_terms")
    op.drop_column("chunks", "token_count")
