"""chunk ordinal unique

Revision ID: 0011_chunk_ordinal_unique
Revises: 0010_single_user_cleanup
Create Date: 2026-11-18

同一文档的片段序号必须唯一。历史数据可能因为并发重试留下重复片段，
先保留 id 最小的一条，再加唯一索引，避免迁移直接失败。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0011_chunk_ordinal_unique"
down_revision: str | None = "0010_single_user_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM chunks a
        USING chunks b
        WHERE a.document_id = b.document_id
          AND a.ordinal = b.ordinal
          AND a.id > b.id
        """
    )
    op.create_index(
        "uq_chunks_document_ordinal",
        "chunks",
        ["document_id", "ordinal"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_chunks_document_ordinal", table_name="chunks")
