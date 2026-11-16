"""citation document id

Revision ID: 0004_citation_document_id
Revises: 0003_model_role_preferences
Create Date: 2026-11-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_citation_document_id"
down_revision: str | None = "0003_model_role_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("citations", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "citations_document_id_fkey",
        "citations",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_citations_document_id", "citations", ["document_id"])
    # 已有引用尽量从 chunk 回填 document_id；片段已删除的历史引用保持为空。
    op.execute(
        """
        UPDATE citations AS c
        SET document_id = ch.document_id
        FROM chunks AS ch
        WHERE c.chunk_id = ch.id AND c.document_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_citations_document_id", table_name="citations")
    op.drop_constraint(
        "citations_document_id_fkey", "citations", type_="foreignkey"
    )
    op.drop_column("citations", "document_id")
