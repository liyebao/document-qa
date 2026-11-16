"""document sources

Revision ID: 0005_document_sources
Revises: 0004_citation_document_id
Create Date: 2026-11-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_document_sources"
down_revision: str | None = "0004_citation_document_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'upload'"),
        ),
    )
    op.add_column("documents", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "fetched_at")
    op.drop_column("documents", "source_url")
    op.drop_column("documents", "source_type")
