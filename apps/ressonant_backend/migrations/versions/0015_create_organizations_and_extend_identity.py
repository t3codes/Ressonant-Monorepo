"""create organizations and extend identity

Revision ID: 0015
Revises: 0014
"""

import re
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_ORGANIZATIONS = sa.table(
    "organizations",
    sa.column("id", sa.Uuid(as_uuid=False)),
    sa.column("name", sa.String()),
    sa.column("slug", sa.String()),
)
_ORGANIZATION_MEMBERS = sa.table(
    "organization_members",
    sa.column("organization_id", sa.Uuid(as_uuid=False)),
    sa.column("user_id", sa.Uuid(as_uuid=False)),
    sa.column("role", sa.String()),
    sa.column("status", sa.String()),
)
_WORKSPACES = sa.table(
    "workspaces",
    sa.column("id", sa.Uuid(as_uuid=False)),
    sa.column("organization_id", sa.Uuid(as_uuid=False)),
)
_TEAMS = sa.table(
    "teams",
    sa.column("id", sa.Uuid(as_uuid=False)),
    sa.column("slug", sa.String()),
    sa.column("key_prefix", sa.String()),
)
_CARDS = sa.table(
    "cards",
    sa.column("id", sa.Uuid(as_uuid=False)),
    sa.column("team_id", sa.Uuid(as_uuid=False)),
    sa.column("key", sa.String()),
)


def _backfill_organizations(bind: sa.Connection) -> None:
    """One organization per pre-existing workspace, owned by that workspace's owner."""
    used_slugs: set[str] = set()
    workspaces = bind.execute(
        sa.text(
            "SELECT id, name, slug, owner_id FROM workspaces "
            "WHERE organization_id IS NULL ORDER BY criado_em, id"
        )
    ).mappings()

    for workspace in workspaces:
        organization_id = str(uuid.uuid4())
        base_slug = workspace["slug"][:100]
        slug = base_slug
        counter = 2
        while slug in used_slugs:
            suffix = f"-{counter}"
            slug = base_slug[: 100 - len(suffix)] + suffix
            counter += 1
        used_slugs.add(slug)

        bind.execute(
            _ORGANIZATIONS.insert().values(
                id=organization_id,
                name=workspace["name"],
                slug=slug,
            )
        )
        bind.execute(
            _ORGANIZATION_MEMBERS.insert().values(
                organization_id=organization_id,
                user_id=workspace["owner_id"],
                role="owner",
                status="active",
            )
        )
        bind.execute(
            _WORKSPACES.update()
            .where(_WORKSPACES.c.id == workspace["id"])
            .values(organization_id=organization_id)
        )


def _backfill_user_names(bind: sa.Connection) -> None:
    """Derive a display name from the existing e-mail local part, without inventing data."""
    bind.execute(
        sa.text("UPDATE users SET name = left(split_part(email, '@', 1), 100) WHERE name IS NULL")
    )


def _team_prefix(slug: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", slug).upper()[:20] or "TEAM"


def _backfill_team_prefixes(bind: sa.Connection) -> None:
    """Uppercase team slug, unique per workspace, truncated to fit String(20)."""
    used: dict[str, set[str]] = {}
    teams = bind.execute(
        sa.text(
            "SELECT id, workspace_id, slug FROM teams "
            "WHERE key_prefix IS NULL ORDER BY criado_em, id"
        )
    ).mappings()

    for team in teams:
        workspace_id = team["workspace_id"]
        prefixes = used.setdefault(workspace_id, set())
        base = _team_prefix(team["slug"])
        prefix = base
        counter = 2
        while prefix in prefixes:
            suffix = str(counter)
            prefix = base[: 20 - len(suffix)] + suffix
            counter += 1
        prefixes.add(prefix)
        bind.execute(_TEAMS.update().where(_TEAMS.c.id == team["id"]).values(key_prefix=prefix))


def _backfill_card_keys(bind: sa.Connection) -> None:
    """Sequential <PREFIX>-<N> keys per team, ordered by criado_em and id."""
    unknown_teams = bind.execute(
        sa.text(
            "SELECT count(*) FROM cards c LEFT JOIN teams t ON t.id = c.team_id "
            "WHERE c.team_id IS NULL OR t.id IS NULL"
        )
    ).scalar_one()
    if unknown_teams:
        raise RuntimeError(f"{unknown_teams} card(s) reference a missing team")

    prefixes = {
        row["id"]: row["key_prefix"]
        for row in bind.execute(sa.text("SELECT id, key_prefix FROM teams")).mappings()
    }
    for team_id in sorted(prefixes):
        cards = bind.execute(
            sa.text("SELECT id FROM cards WHERE team_id = :team_id ORDER BY criado_em, id"),
            {"team_id": team_id},
        ).scalars()
        for sequence, card_id in enumerate(cards, start=1):
            key = f"{prefixes[team_id]}-{sequence}"[:50]
            bind.execute(_CARDS.update().where(_CARDS.c.id == card_id).values(key=key))


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "organization_members",
        sa.Column("organization_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "user_id"),
    )
    op.create_index(
        "uq_organization_members_active_owner",
        "organization_members",
        ["organization_id"],
        unique=True,
        sqlite_where=sa.text("role = 'owner' AND status = 'active'"),
        postgresql_where=sa.text("role = 'owner' AND status = 'active'"),
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_index("ix_invitations_workspace_id", "invitations", ["workspace_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)

    op.add_column("workspaces", sa.Column("organization_id", sa.Uuid(as_uuid=False), nullable=True))
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    op.create_foreign_key(
        "fk_workspaces_organization_id_organizations",
        "workspaces",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column("users", sa.Column("name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("title", sa.String(length=100), nullable=True))
    op.add_column(
        "users", sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("teams", sa.Column("key_prefix", sa.String(length=20), nullable=True))
    op.add_column("cards", sa.Column("key", sa.String(length=50), nullable=True))

    bind = op.get_bind()
    _backfill_organizations(bind)
    op.alter_column(
        "workspaces", "organization_id", existing_type=sa.Uuid(as_uuid=False), nullable=False
    )
    _backfill_user_names(bind)
    _backfill_team_prefixes(bind)
    _backfill_card_keys(bind)

    op.create_unique_constraint(
        "uq_teams_workspace_key_prefix", "teams", ["workspace_id", "key_prefix"]
    )
    op.create_unique_constraint("uq_cards_team_key", "cards", ["team_id", "key"])
    op.alter_column("teams", "key_prefix", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("cards", "key", existing_type=sa.String(length=50), nullable=False)


def downgrade() -> None:
    op.alter_column("cards", "key", existing_type=sa.String(length=50), nullable=True)
    op.alter_column("teams", "key_prefix", existing_type=sa.String(length=20), nullable=True)
    op.drop_constraint("uq_cards_team_key", "cards", type_="unique")
    op.drop_constraint("uq_teams_workspace_key_prefix", "teams", type_="unique")
    op.drop_column("cards", "key")
    op.drop_column("teams", "key_prefix")

    op.drop_column("users", "profile_completed_at")
    op.drop_column("users", "title")
    op.drop_column("users", "name")

    op.drop_constraint(
        "fk_workspaces_organization_id_organizations", "workspaces", type_="foreignkey"
    )
    op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
    op.drop_column("workspaces", "organization_id")

    op.drop_table("invitations")
    op.drop_index(
        "uq_organization_members_active_owner",
        table_name="organization_members",
        sqlite_where=sa.text("role = 'owner' AND status = 'active'"),
        postgresql_where=sa.text("role = 'owner' AND status = 'active'"),
    )
    op.drop_table("organization_members")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
