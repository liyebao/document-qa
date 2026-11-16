"""model role preferences

Revision ID: 0003_model_role_preferences
Revises: 0002_search_indexes
Create Date: 2026-11-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_model_role_preferences"
down_revision: str | None = "0002_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_embedding_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("preferred_chat_provider", sa.String(length=50), nullable=True),
    )
    # 保持升级前的“最近更新配置”行为，避免已有用户在升级后突然失去默认模型。
    op.execute(
        """
        UPDATE users AS u
        SET preferred_chat_provider = (
            SELECT m.provider_key
            FROM model_provider_configs AS m
            WHERE m.user_id = u.id
            ORDER BY m.updated_at DESC
            LIMIT 1
        )
        WHERE u.preferred_chat_provider IS NULL
        """
    )
    op.execute(
        """
        UPDATE users AS u
        SET preferred_embedding_provider = (
            SELECT m.provider_key
            FROM model_provider_configs AS m
            WHERE m.user_id = u.id AND m.embedding_model <> ''
            ORDER BY m.updated_at DESC
            LIMIT 1
        )
        WHERE u.preferred_embedding_provider IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_chat_provider")
    op.drop_column("users", "preferred_embedding_provider")
