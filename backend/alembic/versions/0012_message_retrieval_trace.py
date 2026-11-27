"""message retrieval trace

Revision ID: 0012_message_retrieval_trace
Revises: 0011_chunk_ordinal_unique
Create Date: 2026-11-27

助手消息保存一份精简检索轨迹，供历史会话回看「已检索 / 已浏览」。
不含片段正文，老记录默认空对象。
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_message_retrieval_trace"
down_revision: str | None = "0011_chunk_ordinal_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "retrieval_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "retrieval_trace")
