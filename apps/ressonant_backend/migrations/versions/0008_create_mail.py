"""create mail tables: emails

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("sender_id", sa.Uuid(as_uuid=False), nullable=False, index=True),
        sa.Column("recipient_ids", sa.Text(), nullable=False),
        sa.Column("cc_ids", sa.Text(), nullable=True),
        sa.Column("bcc_ids", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Uuid(as_uuid=False), nullable=True, index=True),
        sa.Column("is_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("forwarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attachments", sa.Text(), nullable=True),
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
    op.drop_table("emails")
