"""granular workspace capability grants

Revision ID: 0024_capability_grants
Revises: 0023_taxonomy_soft_disable
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_capability_grants"
down_revision = "0023_taxonomy_soft_disable"
branch_labels = None
depends_on = None

_TABLE = "workspace_capability_grants"
_UQ_ACTIVE = "uq_workspace_capability_grants_active"
_IX_WORKSPACE_USER = "ix_workspace_capability_grants_workspace_id_user_id"
_CK_EFFECT = "ck_workspace_capability_grants_effect"


def upgrade() -> None:
    # Shape follows PERMISOES-GRANULARES-CONTRATO §1 verbatim: no capability CHECK
    # (the 17 names are validated by the backend), granted_by_id keeps the default
    # NO ACTION and revoked_by_id has no FK because the contract declares none.
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            sa.Uuid(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column(
            "granted_by_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id"),
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
        sa.Column("revoked_by_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("effect IN ('allow', 'deny')", name=_CK_EFFECT),
    )
    op.create_index(
        _UQ_ACTIVE,
        _TABLE,
        ["workspace_id", "user_id", "capability"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(_IX_WORKSPACE_USER, _TABLE, ["workspace_id", "user_id"])


def downgrade() -> None:
    op.drop_index(_IX_WORKSPACE_USER, table_name=_TABLE)
    op.drop_index(_UQ_ACTIVE, table_name=_TABLE)
    op.drop_table(_TABLE)
