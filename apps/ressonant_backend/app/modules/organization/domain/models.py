import uuid
from datetime import datetime

import sqlalchemy as sa
from app.database.engine import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, synonym


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    corporate_domain: Mapped[str | None] = mapped_column(String(254), nullable=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # owner|admin|member|billing_owner
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # active|inactive
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        sa.Index(
            "uq_organization_members_active_owner",
            "organization_id",
            unique=True,
            sqlite_where=sa.text("role = 'owner' AND status = 'active'"),
            postgresql_where=sa.text("role = 'owner' AND status = 'active'"),
        ),
    )


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    personal_email: Mapped[str] = mapped_column(String(254), nullable=False)
    # Temporary alias: backend services/tests still use the old attribute name.
    email = synonym("personal_email")
    corporate_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    invitee_name: Mapped[str | None] = mapped_column(String(254), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    send_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    invited_by_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    team_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reservation_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("true"), nullable=False
    )

    __table_args__ = (
        sa.Index(
            "uq_invitation_pending_org_ws_email",
            "organization_id",
            "workspace_id",
            "personal_email",
            unique=True,
            sqlite_where=sa.text(
                "accepted_at IS NULL AND revoked_at IS NULL AND declined_at IS NULL"
            ),
            postgresql_where=sa.text(
                "accepted_at IS NULL AND revoked_at IS NULL AND declined_at IS NULL"
            ),
        ),
        sa.Index(
            "uq_invitations_active_corporate_email",
            "corporate_email",
            unique=True,
            sqlite_where=sa.text("reservation_active = true"),
            postgresql_where=sa.text("reservation_active = true"),
        ),
    )
