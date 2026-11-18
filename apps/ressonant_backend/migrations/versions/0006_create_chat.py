"""create chat tables: channels, conversations, messages

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("member_ids", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("status_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("member_ids", sa.Text(), nullable=False),
        sa.Column("status_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("room_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("room_kind", sa.String(20), nullable=False),
        sa.Column("author_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True, index=True),
        sa.Column("attachments", sa.Text(), nullable=True),
        sa.Column("mention_ids", sa.Text(), nullable=True),
        sa.Column("status_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("channels")
