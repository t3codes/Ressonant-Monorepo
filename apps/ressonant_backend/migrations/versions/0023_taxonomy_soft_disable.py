"""soft-disable taxonomy values and enforce append-only taxonomy grants

Revision ID: 0023_taxonomy_soft_disable
Revises: 0022_chat_notification_context
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_taxonomy_soft_disable"
down_revision = "0022_chat_notification_context"
branch_labels = None
depends_on = None

_UQ_TAXONOMY = "uq_card_taxonomy_workspace_kind_name"
_IX_DEACTIVATED_BY = "ix_card_taxonomy_desativado_by_id"
_GUARD_FUNCTION = "workspace_taxonomy_grants_append_only"
_GUARD_TRIGGER = "workspace_taxonomy_grants_append_only"


def _create_guard_function() -> str:
    """Invoker-rights guard: no dynamic SQL and no privilege escalation.

    0017 uses the same shape (plain plpgsql trigger, RAISE insufficient_privilege).
    Unlike audit_events, UPDATE is legitimate here (the revoke path), so a
    blanket REVOKE UPDATE/DELETE would break the feature; the guard is per field.
    search_path is pinned without SECURITY DEFINER to avoid operator shadowing.
    """
    return f"""
        CREATE OR REPLACE FUNCTION {_GUARD_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'workspace_taxonomy_grants is append-only: revoke instead of delete'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF OLD.id IS DISTINCT FROM NEW.id
               OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id
               OR OLD.user_id IS DISTINCT FROM NEW.user_id
               OR OLD.granted_by_id IS DISTINCT FROM NEW.granted_by_id
               OR OLD.reason IS DISTINCT FROM NEW.reason
               OR OLD.created_at IS DISTINCT FROM NEW.created_at
            THEN
                RAISE EXCEPTION 'workspace_taxonomy_grants: immutable column changed'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF OLD.revoked_at IS NOT NULL THEN
                IF OLD.revoked_at IS DISTINCT FROM NEW.revoked_at
                   OR OLD.revoked_by_id IS DISTINCT FROM NEW.revoked_by_id
                   OR OLD.revoke_reason IS DISTINCT FROM NEW.revoke_reason
                   OR OLD.updated_at IS DISTINCT FROM NEW.updated_at
                THEN
                    RAISE EXCEPTION 'workspace_taxonomy_grants: revoked grant is immutable'
                        USING ERRCODE = 'insufficient_privilege';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.revoked_at IS NULL THEN
                RAISE EXCEPTION 'workspace_taxonomy_grants: only revocation may update a grant'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            RETURN NEW;
        END;
        $$
    """


def upgrade() -> None:
    # CYB-TAX-001: logical deactivation, no DELETE and no rename of a live value.
    op.add_column(
        "card_taxonomy", sa.Column("desativado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "card_taxonomy",
        sa.Column(
            "desativado_by_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(_IX_DEACTIVATED_BY, "card_taxonomy", ["desativado_by_id"])
    op.add_column("card_taxonomy", sa.Column("deactivate_reason", sa.Text(), nullable=True))

    # Same name, now partial: a deactivated name can be reused in the workspace.
    op.drop_constraint(_UQ_TAXONOMY, "card_taxonomy", type_="unique")
    op.create_index(
        _UQ_TAXONOMY,
        "card_taxonomy",
        ["workspace_id", "kind", "name"],
        unique=True,
        sqlite_where=sa.text("desativado_em IS NULL"),
        postgresql_where=sa.text("desativado_em IS NULL"),
    )

    # CYB-TAX-007: grant history is append-only at the database level.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(_create_guard_function()))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_GUARD_TRIGGER} ON workspace_taxonomy_grants"))
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_GUARD_TRIGGER}
                BEFORE DELETE OR UPDATE ON workspace_taxonomy_grants
                FOR EACH ROW EXECUTE FUNCTION {_GUARD_FUNCTION}()
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            """
            SELECT count(*)
              FROM (
                    SELECT workspace_id, kind, name
                      FROM card_taxonomy
                     GROUP BY workspace_id, kind, name
                    HAVING count(*) > 1
                   ) AS duplicated
            """
        )
    ).scalar_one()
    if duplicates:
        raise RuntimeError(
            "Cannot downgrade 0023: deactivated values reuse names; the old total UNIQUE "
            "constraint would reject them."
        )

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_GUARD_TRIGGER} ON workspace_taxonomy_grants"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_GUARD_FUNCTION}()"))

    op.drop_index(_UQ_TAXONOMY, table_name="card_taxonomy")
    op.create_unique_constraint(_UQ_TAXONOMY, "card_taxonomy", ["workspace_id", "kind", "name"])
    op.drop_index(_IX_DEACTIVATED_BY, table_name="card_taxonomy")
    op.drop_column("card_taxonomy", "deactivate_reason")
    op.drop_column("card_taxonomy", "desativado_by_id")
    op.drop_column("card_taxonomy", "desativado_em")
