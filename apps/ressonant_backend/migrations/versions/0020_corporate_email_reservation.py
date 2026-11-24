"""corporate e-mail, invitation reservation and optional invite-signup fields

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_RESERVATION_TRIGGER = "trg_invitations_reservation_active"
_SET_RESERVATION_FN = "set_invitation_reservation_active"
_EXPIRE_RESERVATIONS_FN = "expire_invitation_reservations"


def upgrade() -> None:
    # Organizations: mandatory at signup (enforced in the backend); nullable in
    # the database so legacy rows without an active owner remain valid.
    op.add_column(
        "organizations", sa.Column("corporate_domain", sa.String(length=254), nullable=True)
    )
    # Derive from the active owner's e-mail domain; no owner => keep NULL.
    op.execute(
        sa.text(
            """
            UPDATE organizations AS o
               SET corporate_domain = (
                   SELECT lower(split_part(u.email, '@', 2))
                     FROM organization_members AS om
                     JOIN users AS u ON u.id = om.user_id
                    WHERE om.organization_id = o.id
                      AND om.role = 'owner'
                      AND om.status = 'active'
                      AND u.email LIKE '%@%'
                    LIMIT 1
               )
             WHERE o.corporate_domain IS NULL
            """
        )
    )

    # Invite registration asks only for name, CPF and password: no invented
    # phone number or age for invitees.
    op.alter_column("users", "idade", existing_type=sa.Integer(), nullable=True)
    op.alter_column("users", "telefone", existing_type=sa.String(length=11), nullable=True)
    op.add_column("users", sa.Column("corporate_email", sa.String(length=254), nullable=True))
    op.create_index("ix_users_corporate_email", "users", ["corporate_email"], unique=True)
    op.add_column("users", sa.Column("personal_email", sa.String(length=254), nullable=True))

    # Rename in place: existing invitation addresses are preserved.
    op.execute(sa.text("ALTER TABLE invitations RENAME COLUMN email TO personal_email"))
    op.add_column("invitations", sa.Column("corporate_email", sa.String(length=254), nullable=True))
    op.add_column("invitations", sa.Column("invitee_name", sa.String(length=254), nullable=True))
    op.add_column(
        "invitations",
        sa.Column(
            "team_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_invitations_team_id", "invitations", ["team_id"])
    op.add_column(
        "invitations",
        sa.Column(
            "reservation_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Legacy invitations: the current address is also the corporate address.
    op.execute(
        sa.text(
            """
            UPDATE invitations
               SET corporate_email = personal_email
             WHERE corporate_email IS NULL
               AND personal_email IS NOT NULL
            """
        )
    )
    # Legacy settled/expired invitations must not hold a reservation.
    op.execute(
        sa.text(
            """
            UPDATE invitations
               SET reservation_active = false
             WHERE accepted_at IS NOT NULL
                OR revoked_at IS NOT NULL
                OR declined_at IS NOT NULL
                OR expires_at <= now()
            """
        )
    )
    # now() is not IMUTABLE, so expiry cannot live in the partial index
    # predicate. The boolean flag plus the periodic function do that job.
    op.create_index(
        "uq_invitations_active_corporate_email",
        "invitations",
        ["corporate_email"],
        unique=True,
        postgresql_where=sa.text("reservation_active = true"),
        sqlite_where=sa.text("reservation_active = true"),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # A BEFORE trigger can assign NEW directly; an AFTER trigger cannot.
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_SET_RESERVATION_FN}()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.accepted_at IS NOT NULL
                       OR NEW.revoked_at IS NOT NULL
                       OR NEW.declined_at IS NOT NULL
                       OR NEW.expires_at <= now()
                    THEN
                        NEW.reservation_active := false;
                    END IF;
                    RETURN NEW;
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_RESERVATION_TRIGGER}
                BEFORE INSERT OR UPDATE ON invitations
                FOR EACH ROW EXECUTE FUNCTION {_SET_RESERVATION_FN}();
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_EXPIRE_RESERVATIONS_FN}()
                RETURNS integer
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    affected integer;
                BEGIN
                    UPDATE invitations
                       SET reservation_active = false
                     WHERE reservation_active = true
                       AND expires_at <= now();
                    GET DIAGNOSTICS affected = ROW_COUNT;
                    RETURN affected;
                END;
                $$;
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_RESERVATION_TRIGGER} ON invitations"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_SET_RESERVATION_FN}()"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_EXPIRE_RESERVATIONS_FN}()"))

    op.drop_index("uq_invitations_active_corporate_email", table_name="invitations")
    op.drop_index("ix_invitations_team_id", table_name="invitations")
    op.drop_column("invitations", "reservation_active")
    op.drop_column("invitations", "team_id")
    op.drop_column("invitations", "invitee_name")
    op.drop_column("invitations", "corporate_email")
    op.execute(sa.text("ALTER TABLE invitations RENAME COLUMN personal_email TO email"))

    op.drop_index("ix_users_corporate_email", table_name="users")
    op.drop_column("users", "personal_email")
    op.drop_column("users", "corporate_email")
    # Rows created after 0020 with NULL phone/age make this downgrade fail by
    # design: no placeholder value is invented to satisfy the old constraint.
    op.alter_column("users", "telefone", existing_type=sa.String(length=11), nullable=False)
    op.alter_column("users", "idade", existing_type=sa.Integer(), nullable=False)

    op.drop_column("organizations", "corporate_domain")
