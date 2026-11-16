"""search indexes and auth token version

Revision ID: 0002_search_indexes
Revises: 0001_initial
Create Date: 2026-11-12

向量列允许不同资料集使用不同维度，因此不能直接对 embedding 建单一 HNSW 索引。
这里按常见维度建立部分表达式索引，查询端只在维度匹配时使用对应表达式，
其他维度自动退化为精确扫描。关键词检索使用 pg_trgm 加速 ILIKE 子串匹配。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_search_indexes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# HNSW 对 vector 类型最多支持 2000 维，3072 维使用 halfvec。
_VECTOR_INDEXES: tuple[tuple[str, int, str], ...] = (
    ("ix_chunks_embedding_768", 768, "vector"),
    ("ix_chunks_embedding_1024", 1024, "vector"),
    ("ix_chunks_embedding_1536", 1536, "vector"),
    ("ix_chunks_embedding_3072", 3072, "halfvec"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_search_text_trgm "
        "ON chunks USING gin (search_text gin_trgm_ops)"
    )

    for index_name, dimension, vector_type in _VECTOR_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON chunks USING hnsw ((embedding::{vector_type}({dimension})) "
            f"{vector_type}_cosine_ops) "
            f"WHERE vector_dims(embedding) = {dimension}"
        )

    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    for index_name, _, _ in _VECTOR_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_text_trgm")
