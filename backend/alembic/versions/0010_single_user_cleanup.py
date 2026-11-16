"""single user cleanup

Revision ID: 0010_single_user_cleanup
Revises: 0009_password_reset_codes
Create Date: 2026-11-14

单用户本地模式不再需要登录密码和密码重置验证码。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_single_user_cleanup"
down_revision: str | None = "0009_password_reset_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("password_reset_codes")
    op.drop_column("users", "token_version")
    op.drop_column("users", "password_hash")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
            server_default="",
        ),
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
    op.alter_column("users", "password_hash", server_default=None)
    op.alter_column("users", "token_version", server_default=None)

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
