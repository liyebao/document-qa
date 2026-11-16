"""password reset codes

Revision ID: 0009_password_reset_codes
Revises: 0008_processing_jobs
Create Date: 2026-11-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_password_reset_codes"
down_revision: str | None = "0008_processing_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_codes_user_id", "password_reset_codes", ["user_id"]
    )
    op.create_index(
        "ix_password_reset_codes_user_created",
        "password_reset_codes",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_codes_user_created", table_name="password_reset_codes"
    )
    op.drop_index("ix_password_reset_codes_user_id", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
