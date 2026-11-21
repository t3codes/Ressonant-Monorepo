"""generalize audit events and enforce append only

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_TRIGGER = "audit_events_append_only"
_FUNCTION = "audit_events_append_only"
_FK_ORGANIZATION = "fk_audit_events_organization_id_organizations"
_CHECK_SCOPE = "ck_audit_events_scope"


def _quoted_application_role(bind: sa.Connection) -> str:
    """Quote the role from the connection URL; never log or embed credentials."""
    url = getattr(bind, "url", None) or getattr(getattr(bind, "engine", None), "url", None)
    username = getattr(url, "username", None)
    if not username:
        raise RuntimeError(
            "Cannot enforce append-only on audit_events: the database URL has no username."
        )
    return bind.dialect.identifier_preparer.quote(username)


def _enforce_append_only(bind: sa.Connection) -> None:
    role = _quoted_application_role(bind)
    op.execute(
        sa.text(f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events is append-only: record a new event instead'
                    USING ERRCODE = 'insufficient_privilege';
            END;
            $$
        """)
    )
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON audit_events"))
    op.execute(
        sa.text(f"""
            CREATE TRIGGER {_TRIGGER}
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()
        """)
    )
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE audit_events FROM {role}"))


def _restore_writes(bind: sa.Connection) -> None:
    role = _quoted_application_role(bind)
    op.execute(sa.text(f"GRANT UPDATE, DELETE ON TABLE audit_events TO {role}"))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON audit_events"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION}()"))


def upgrade() -> None:
    op.add_column(
        "audit_events", sa.Column("organization_id", sa.Uuid(as_uuid=False), nullable=True)
    )
    op.create_index(
        op.f("ix_audit_events_organization_id"),
        "audit_events",
        ["organization_id"],
        unique=False,
    )
    op.create_foreign_key(
        _FK_ORGANIZATION,
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("audit_events", sa.Column("actor_role", sa.String(length=50), nullable=True))
    op.add_column("audit_events", sa.Column("permission_version", sa.Integer(), nullable=True))
    op.add_column(
        "audit_events",
        sa.Column("scope", sa.String(length=20), server_default="workspace", nullable=False),
    )
    op.create_check_constraint(
        _CHECK_SCOPE,
        "audit_events",
        "scope IN ('organization', 'workspace', 'card')",
    )
    op.execute(sa.text("UPDATE audit_events SET scope = 'workspace' WHERE scope IS NULL"))
    op.alter_column(
        "audit_events", "workspace_id", existing_type=sa.Uuid(as_uuid=False), nullable=True
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _enforce_append_only(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _restore_writes(bind)

    unscoped = bind.execute(
        sa.text("SELECT count(*) FROM audit_events WHERE workspace_id IS NULL")
    ).scalar_one()
    if unscoped:
        raise RuntimeError(
            f"Cannot downgrade 0017: {unscoped} audit event(s) have no workspace_id."
        )

    op.drop_constraint(_CHECK_SCOPE, "audit_events", type_="check")
    op.alter_column(
        "audit_events", "workspace_id", existing_type=sa.Uuid(as_uuid=False), nullable=False
    )
    op.drop_column("audit_events", "scope")
    op.drop_column("audit_events", "permission_version")
    op.drop_column("audit_events", "actor_role")
    op.drop_constraint(_FK_ORGANIZATION, "audit_events", type_="foreignkey")
    op.drop_index(op.f("ix_audit_events_organization_id"), table_name="audit_events")
    op.drop_column("audit_events", "organization_id")
