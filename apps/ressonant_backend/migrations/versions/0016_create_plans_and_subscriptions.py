"""create plans and subscriptions

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
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

# Preços são proposta de planejamento (D3), não valor contratado. Nenhuma cobrança real.
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


def _seed_catalog(bind: sa.Connection) -> None:
    for plan in _CATALOG:
        bind.execute(_PLANS.insert().values(**plan))


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("seat_limit", sa.Integer(), nullable=True),
        sa.Column("overage_cents_per_seat", sa.Integer(), nullable=True),
        sa.Column("trial_days", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_code"), "plans", ["code"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("plan_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("seats_purchased", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gateway_ref", sa.String(length=100), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscriptions_organization_id"), "subscriptions", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_subscriptions_plan_id"), "subscriptions", ["plan_id"], unique=False)
    op.create_index(
        "uq_subscriptions_one_active_per_organization",
        "subscriptions",
        ["organization_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )

    _seed_catalog(op.get_bind())


def downgrade() -> None:
    op.drop_index(
        "uq_subscriptions_one_active_per_organization",
        table_name="subscriptions",
        sqlite_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )
    op.drop_index(op.f("ix_subscriptions_plan_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_organization_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_plans_code"), table_name="plans")
    op.drop_table("plans")
