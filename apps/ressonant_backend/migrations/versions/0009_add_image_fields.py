"""add image fields to users and workspaces

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_content_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_size_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("logo_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("logo_content_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("logo_size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_size_bytes")
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_url")
    op.drop_column("workspaces", "logo_size_bytes")
    op.drop_column("workspaces", "logo_content_type")
    op.drop_column("workspaces", "logo_url")
