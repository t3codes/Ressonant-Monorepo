"""add block fields to cards

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cards", sa.Column("block_reason", sa.Text(), nullable=True))
    op.add_column("cards", sa.Column("blocked_by", sa.Uuid(as_uuid=False), nullable=True))
    op.add_column("cards", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_cards_blocked_by", "cards", ["blocked_by"])


def downgrade() -> None:
    op.drop_index("ix_cards_blocked_by", table_name="cards")
    op.drop_column("cards", "blocked_at")
    op.drop_column("cards", "blocked_by")
    op.drop_column("cards", "block_reason")
    op.drop_column("cards", "is_blocked")
