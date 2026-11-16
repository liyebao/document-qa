"""rerank model per provider config

Revision ID: 0007_rerank_model
Revises: 0006_bm25_terms
Create Date: 2026-11-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_rerank_model"
down_revision: str | None = "0006_bm25_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_provider_configs",
        sa.Column(
            "rerank_model",
            sa.String(length=120),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("model_provider_configs", "rerank_model")
