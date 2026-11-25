"""workspace card taxonomy catalog and taxonomy manage grants

Revision ID: 0021_card_taxonomy
Revises: 0020
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_card_taxonomy"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Workspace-scoped catalog of category names and release ("fix_version")
    # values. Existing cards.fix_version and cards.version are NOT changed:
    # the application validates the free-text value against this catalog.
    op.create_table(
        "card_taxonomy",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('category', 'version')", name="ck_card_taxonomy_kind"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_card_taxonomy_name_nonblank"),
        sa.UniqueConstraint(
            "workspace_id", "kind", "name", name="uq_card_taxonomy_workspace_kind_name"
        ),
    )
    # The unique constraint already indexes (workspace_id, kind, name); these
    # two indexes serve the FK-side lookups (workspace deletion and creator).
    op.create_index("ix_card_taxonomy_workspace_id", "card_taxonomy", ["workspace_id"])
    op.create_index("ix_card_taxonomy_created_by_id", "card_taxonomy", ["created_by_id"])

    # Fine-grained capability, not a management level: reusing "modify" would
    # also grant team/member/column administration. Shape mirrors the existing
    # workspace_management_grants (0014): soft revoke + partial unique index.
    op.create_table(
        "workspace_taxonomy_grants",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_workspace_taxonomy_grants_workspace_id",
        "workspace_taxonomy_grants",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_taxonomy_grants_user_id", "workspace_taxonomy_grants", ["user_id"]
    )
    op.create_index(
        "ix_workspace_taxonomy_grants_granted_by_id",
        "workspace_taxonomy_grants",
        ["granted_by_id"],
    )
    op.create_index(
        "ix_workspace_taxonomy_grants_revoked_by_id",
        "workspace_taxonomy_grants",
        ["revoked_by_id"],
    )
    op.create_index(
        "uq_workspace_taxonomy_grants_active",
        "workspace_taxonomy_grants",
        ["workspace_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workspace_taxonomy_grants_active", table_name="workspace_taxonomy_grants")
    op.drop_index(
        "ix_workspace_taxonomy_grants_revoked_by_id", table_name="workspace_taxonomy_grants"
    )
    op.drop_index(
        "ix_workspace_taxonomy_grants_granted_by_id", table_name="workspace_taxonomy_grants"
    )
    op.drop_index("ix_workspace_taxonomy_grants_user_id", table_name="workspace_taxonomy_grants")
    op.drop_index(
        "ix_workspace_taxonomy_grants_workspace_id", table_name="workspace_taxonomy_grants"
    )
    op.drop_table("workspace_taxonomy_grants")

    op.drop_index("ix_card_taxonomy_created_by_id", table_name="card_taxonomy")
    op.drop_index("ix_card_taxonomy_workspace_id", table_name="card_taxonomy")
    op.drop_table("card_taxonomy")
