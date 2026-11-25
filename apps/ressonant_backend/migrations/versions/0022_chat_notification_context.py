"""add chat context columns to notifications

Revision ID: 0022_chat_notification_context
Revises: 0021_card_taxonomy
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_chat_notification_context"
down_revision = "0021_card_taxonomy"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("workspace_id", sa.Uuid(as_uuid=False)),
    ("actor_id", sa.Uuid(as_uuid=False)),
    ("message_id", sa.Uuid(as_uuid=False)),
    ("room_id", sa.Uuid(as_uuid=False)),
    ("room_kind", sa.String(length=20)),
)


def upgrade() -> None:
    # Aditiva: linhas antigas ficam com NULL e continuam legíveis.
    for name, column in _COLUMNS:
        op.add_column("notifications", sa.Column(name, column, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("notifications", name)
