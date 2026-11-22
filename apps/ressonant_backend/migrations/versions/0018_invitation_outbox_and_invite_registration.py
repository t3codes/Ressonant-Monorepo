"""invitation lifecycle, outbox, and invite registration support

Revision ID: 0018_invitation_outbox
Revises: 0017_generalize_audit_events_and_enforce_append_only
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_invitation_outbox"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invitations", sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("invitations", sa.Column("resent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "invitations", sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "invitations",
        sa.Column("send_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "invitations",
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("recipient_email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_email_outbox_event_type", "email_outbox", ["event_type"])
    op.create_index("ix_email_outbox_recipient_email", "email_outbox", ["recipient_email"])
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"])
    op.create_index("ix_email_outbox_next_attempt_at", "email_outbox", ["next_attempt_at"])
    op.create_index("ix_email_outbox_dedupe_key", "email_outbox", ["dedupe_key"], unique=True)
    # Prevent concurrent duplicate pending invitations for same org/workspace/email.
    op.create_index(
        "uq_invitation_pending_org_ws_email",
        "invitations",
        ["organization_id", "workspace_id", "email"],
        unique=True,
        postgresql_where=sa.text(
            "accepted_at IS NULL AND revoked_at IS NULL AND declined_at IS NULL"
        ),
        sqlite_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL AND declined_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_invitation_pending_org_ws_email", table_name="invitations")
    op.drop_index("ix_email_outbox_dedupe_key", table_name="email_outbox")
    op.drop_index("ix_email_outbox_next_attempt_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_status", table_name="email_outbox")
    op.drop_index("ix_email_outbox_recipient_email", table_name="email_outbox")
    op.drop_index("ix_email_outbox_event_type", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_column("invitations", "atualizado_em")
    op.drop_column("invitations", "send_status")
    op.drop_column("invitations", "last_sent_at")
    op.drop_column("invitations", "resent_at")
    op.drop_column("invitations", "declined_at")
