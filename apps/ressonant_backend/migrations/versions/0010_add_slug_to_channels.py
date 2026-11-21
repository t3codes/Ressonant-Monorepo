"""add slug to channels

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column(
            "slug", sa.String(100), nullable=False, unique=True, index=True, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("channels", "slug")
