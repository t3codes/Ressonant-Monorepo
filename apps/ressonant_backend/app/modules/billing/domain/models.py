import uuid
from datetime import datetime

import sqlalchemy as sa
from app.database.engine import Base
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

PLAN_CODES = ("inicial", "equipe", "empresa")
SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "canceled")
ACTIVE_SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="monthly", server_default="monthly"
    )  # monthly|yearly|custom
    base_price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    price_per_seat_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    included_seats: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    limits: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'"),
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # Colunas legadas continuam contrato: serviços de billing atuais ainda as leem.
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    seat_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = ilimitado
    overage_cents_per_seat: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # NULL = sem uplift
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, server_default=sa.true(), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly', 'custom')", name="ck_plans_billing_cycle"
        ),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # trialing|active|past_due|canceled
    seats_purchased: Mapped[int] = mapped_column(
        Integer, server_default=sa.text("0"), nullable=False
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gateway_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index(
            "uq_subscriptions_one_active_per_organization",
            "organization_id",
            unique=True,
            sqlite_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
            postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
        ),
    )
