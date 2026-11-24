"""reseed plan catalog idempotently

Revision ID: 0019
Revises: 0018_invitation_outbox
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018_invitation_outbox"
branch_labels = None
depends_on = None

_PLANS = sa.table(
    "plans",
    sa.column("id", sa.Uuid(as_uuid=False)),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("price_cents", sa.Integer()),
    sa.column("currency", sa.String()),
    sa.column("seat_limit", sa.Integer()),
    sa.column("overage_cents_per_seat", sa.Integer()),
    sa.column("trial_days", sa.Integer()),
    sa.column("active", sa.Boolean()),
)

# Exact copy of 0016's catalog: codes, capacities and trial period unchanged.
# Prices are a planning proposal (D3), not a contracted charge.
_CATALOG = (
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "code": "inicial",
        "name": "Inicial",
        "price_cents": 0,
        "currency": "BRL",
        "seat_limit": 3,
        "overage_cents_per_seat": None,
        "trial_days": 14,
        "active": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "code": "equipe",
        "name": "Equipe",
        "price_cents": 4900,
        "currency": "BRL",
        "seat_limit": 15,
        "overage_cents_per_seat": 4900,
        "trial_days": 14,
        "active": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "code": "empresa",
        "name": "Empresa",
        "price_cents": 7900,
        "currency": "BRL",
        "seat_limit": None,
        "overage_cents_per_seat": None,
        "trial_days": 14,
        "active": True,
    },
)


def _insert_catalog(bind: sa.Connection) -> None:
    values = [dict(plan) for plan in _CATALOG]
    dialect = bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        statement = pg_insert(_PLANS).values(values).on_conflict_do_nothing()
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        statement = sqlite_insert(_PLANS).values(values).on_conflict_do_nothing()
    else:  # pragma: no cover - the project targets Postgres; SQLite is test-only
        statement = sa.insert(_PLANS).values(values)
    bind.execute(statement)


def upgrade() -> None:
    # 0016 remains applied: an earlier TRUNCATE emptied the catalog without
    # rewinding alembic_version. DO NOTHING preserves rows in healthy envs.
    _insert_catalog(op.get_bind())


def downgrade() -> None:
    # Intentionally a no-op: deleting catalog rows could break the RESTRICT FK
    # from subscriptions and would destroy data. Rolling back stops at 0018.
    pass
