import uuid
from datetime import UTC, datetime

from app.modules.billing.domain.models import ACTIVE_SUBSCRIPTION_STATUSES, Plan, Subscription
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.teams.domain.models import Team
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
from sqlalchemy import select, text, union, update
from sqlalchemy.orm import Session


class OrganizationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        return self._db

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def get_user_by_id(self, user_id: str) -> User | None:
        if not self._is_uuid(user_id):
            return None
        return self._db.get(User, user_id)

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except ValueError:
            return False

    def get_by_id(self, organization_id: str) -> Organization | None:
        if not self._is_uuid(organization_id):
            return None
        return self._db.get(Organization, organization_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        return self._db.scalar(select(Organization).where(Organization.slug == slug))

    def exists_by_slug(self, slug: str) -> bool:
        return (
            self._db.scalar(select(Organization.id).where(Organization.slug == slug).limit(1))
            is not None
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self._db.scalar(select(User).where(User.email == email))

    def get_team_by_id(self, team_id: str | None) -> Team | None:
        if not team_id or not self._is_uuid(team_id):
            return None
        return self._db.get(Team, team_id)

    def get_team_in_workspace(self, team_id: str | None, workspace_id: str) -> Team | None:
        """Time apenas se pertencer ao workspace — usado em criação e leitura (CYB-002)."""
        if not team_id or not self._is_uuid(team_id) or not self._is_uuid(workspace_id):
            return None
        return self._db.scalar(
            select(Team).where(Team.id == team_id, Team.workspace_id == workspace_id)
        )

    def expire_invitation_reservations(self) -> int:
        """Desativa reservas vencidas antes de consultar disponibilidade.

        Em PostgreSQL chama a função criada na migration 0020; no SQLite dos
        testes aplica a mesma transição com uma única instrução SQL.
        """
        if self._db.get_bind().dialect.name != "sqlite":
            result = self._db.execute(text("SELECT expire_invitation_reservations()"))
            return int(result.scalar_one())

        result = self._db.execute(
            update(Invitation)
            .where(
                Invitation.reservation_active.is_(True),
                Invitation.expires_at <= datetime.now(UTC),
            )
            .values(reservation_active=False)
        )
        return int(result.rowcount or 0)

    def first_available_corporate_email(self, candidates: list[str]) -> str | None:
        """Primeiro candidato livre, com uma única consulta para as 3 origens.

        A serialização é feita por `lock_organization` no service; o índice
        parcial `uq_invitations_active_corporate_email` é a barreira final.
        """
        if not candidates:
            return None
        now = datetime.now(UTC)
        stmt = union(
            select(User.email).where(User.email.in_(candidates)),
            select(User.corporate_email).where(User.corporate_email.in_(candidates)),
            select(Invitation.corporate_email).where(
                Invitation.corporate_email.in_(candidates),
                Invitation.reservation_active.is_(True),
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.declined_at.is_(None),
                Invitation.expires_at > now,
            ),
        )
        taken = {str(value).lower() for value in self._db.scalars(stmt) if value}
        return next((candidate for candidate in candidates if candidate not in taken), None)

    def get_member(self, organization_id: str, user_id: str) -> OrganizationMember | None:
        if not self._is_uuid(organization_id) or not self._is_uuid(user_id):
            return None
        return self._db.get(OrganizationMember, (organization_id, user_id))

    def get_organization_role(self, organization_id: str, user_id: str) -> str | None:
        member = self.get_member(organization_id, user_id)
        if member is None or member.status != "active":
            return None
        return member.role

    def add(self, organization: Organization) -> Organization:
        self._db.add(organization)
        self._db.flush()
        return organization

    def add_member(self, member: OrganizationMember) -> OrganizationMember:
        self._db.add(member)
        self._db.flush()
        return member

    def list_members(self, organization_id: str) -> list[OrganizationMember]:
        if not self._is_uuid(organization_id):
            return []
        return list(
            self._db.scalars(
                select(OrganizationMember)
                .where(OrganizationMember.organization_id == organization_id)
                .order_by(OrganizationMember.criado_em, OrganizationMember.user_id)
            )
        )

    def list_for_user(self, user_id: str) -> list[tuple[Organization, OrganizationMember]]:
        """Memberships do usuário, da mais antiga para a mais recente."""
        if not self._is_uuid(user_id):
            return []
        stmt = (
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(OrganizationMember.criado_em, Organization.id)
        )
        return [(organization, member) for organization, member in self._db.execute(stmt)]

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        if not self._is_uuid(workspace_id):
            return None
        return self._db.get(Workspace, workspace_id)

    def get_workspace_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    def add_workspace_member(self, member: WorkspaceMember) -> WorkspaceMember:
        self._db.add(member)
        self._db.flush()
        return member

    def get_active_subscription(self, organization_id: str) -> tuple[Subscription, Plan] | None:
        if not self._is_uuid(organization_id):
            return None
        row = self._db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.organization_id == organization_id,
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
            .order_by(Subscription.criado_em, Subscription.id)
            .limit(1)
        ).first()
        return (row[0], row[1]) if row is not None else None

    def count_seats_used(self, organization_id: str, *, now: datetime | None = None) -> int:
        if not self._is_uuid(organization_id):
            return 0
        organization_users = set(
            self._db.scalars(
                select(OrganizationMember.user_id).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.status == "active",
                )
            )
        )
        workspace_users = set(
            self._db.scalars(
                select(WorkspaceMember.user_id)
                .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                .where(Workspace.organization_id == organization_id)
            )
        )
        active_user_ids = organization_users | workspace_users
        active_emails = (
            {
                email.strip().lower()
                for email in self._db.scalars(
                    select(User.email).where(User.id.in_(active_user_ids))
                )
                if isinstance(email, str) and email.strip()
            }
            if active_user_ids
            else set()
        )

        current_time = now or datetime.utcnow()
        pending_emails = set()
        for email, expires_at in self._db.execute(
            select(Invitation.email, Invitation.expires_at).where(
                Invitation.organization_id == organization_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.declined_at.is_(None),
            )
        ):
            normalized = (email or "").strip().lower()
            if not normalized or normalized in active_emails:
                continue
            exp = expires_at
            if exp is None:
                continue
            if exp.tzinfo is not None:
                exp_cmp = exp.replace(tzinfo=None)
            else:
                exp_cmp = exp
            if exp_cmp <= current_time:
                continue
            pending_emails.add(normalized)
        return len(active_user_ids) + len(pending_emails)

    def is_user_counted_in_seats(self, organization_id: str, user_id: str) -> bool:
        if not self._is_uuid(organization_id) or not self._is_uuid(user_id):
            return False
        org_member = self.get_member(organization_id, user_id)
        if org_member is not None and org_member.status == "active":
            return True
        ws_member = self._db.scalar(
            select(WorkspaceMember.user_id)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(Workspace.organization_id == organization_id, WorkspaceMember.user_id == user_id)
            .limit(1)
        )
        return ws_member is not None

    def get_seat_limit(self, organization_id: str) -> tuple[int | None, str]:
        row = self.get_active_subscription(organization_id)
        if row is None:
            # Sem assinatura ativa: usa plano default como no billing para mensagem coerente.
            plan = self._db.scalar(
                select(Plan).where(Plan.code == "inicial", Plan.active.is_(True))
            )
            if plan is None:
                return None, "atual"
            return plan.seat_limit, plan.name
        subscription, plan = row
        limit = plan.seat_limit
        if limit is None:
            return None, plan.name
        return limit + subscription.seats_purchased, plan.name

    def _supports_for_update(self) -> bool:
        bind = self._db.get_bind()
        dialect = bind.dialect
        supports = getattr(dialect, "supports_for_update", None)
        if supports is None:
            supports = dialect.name not in {"sqlite"}
        return bool(supports)

    def get_invitation_by_id(
        self, invitation_id: str, *, for_update: bool = False
    ) -> Invitation | None:
        if not self._is_uuid(invitation_id):
            return None
        stmt = select(Invitation).where(Invitation.id == invitation_id)
        if for_update and self._supports_for_update():
            stmt = stmt.with_for_update()
        return self._db.scalar(stmt)

    def get_invitation_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> Invitation | None:
        stmt = select(Invitation).where(Invitation.token_hash == token_hash)
        if for_update and self._supports_for_update():
            stmt = stmt.with_for_update()
        return self._db.scalar(stmt)

    def lock_organization(self, organization_id: str) -> Organization | None:
        if not self._is_uuid(organization_id):
            return None
        stmt = select(Organization).where(Organization.id == organization_id)
        if self._supports_for_update():
            stmt = stmt.with_for_update()
        return self._db.scalar(stmt)

    def get_pending_invitation(
        self, *, organization_id: str, workspace_id: str, email: str
    ) -> Invitation | None:
        if not self._is_uuid(organization_id) or not self._is_uuid(workspace_id):
            return None
        return self._db.scalar(
            select(Invitation)
            .where(
                Invitation.organization_id == organization_id,
                Invitation.workspace_id == workspace_id,
                Invitation.email == email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.declined_at.is_(None),
            )
            .order_by(Invitation.criado_em.desc(), Invitation.id.desc())
            .limit(1)
        )

    def list_invitations(self, organization_id: str) -> list[Invitation]:
        if not self._is_uuid(organization_id):
            return []
        return list(
            self._db.scalars(
                select(Invitation)
                .where(Invitation.organization_id == organization_id)
                .order_by(Invitation.criado_em.desc(), Invitation.id.desc())
            )
        )

    def add_invitation(self, invitation: Invitation) -> Invitation:
        self._db.add(invitation)
        self._db.flush()
        return invitation

    def mark_invitation_accepted(self, invitation: Invitation, *, accepted_at: datetime) -> None:
        invitation.accepted_at = accepted_at
        invitation.reservation_active = False
        self._db.flush()

    def mark_invitation_revoked(self, invitation: Invitation, *, revoked_at: datetime) -> None:
        invitation.revoked_at = revoked_at
        invitation.reservation_active = False
        self._db.flush()

    def mark_invitation_declined(self, invitation: Invitation, *, declined_at: datetime) -> None:
        invitation.declined_at = declined_at
        invitation.reservation_active = False
        self._db.flush()

    def update_invitation_for_resend(
        self, invitation: Invitation, *, token_hash: str, expires_at: datetime, resent_at: datetime
    ) -> None:
        invitation.token_hash = token_hash
        invitation.expires_at = expires_at
        invitation.resent_at = resent_at
        invitation.send_status = "pending"
        self._db.flush()

    def set_invitation_send_status(
        self, invitation: Invitation, *, send_status: str, last_sent_at: datetime | None = None
    ) -> None:
        invitation.send_status = send_status
        if last_sent_at is not None:
            invitation.last_sent_at = last_sent_at
        self._db.flush()

    def delete_invitation(self, invitation: Invitation) -> None:
        self._db.delete(invitation)
        self._db.flush()

    def commit(self) -> None:
        """Só para consistência de padrão: o orquestrador atômico compartilha uma Session
        e fará um único commit no fim, portanto não deve chamar este método.
        """
        self._db.commit()

    def rollback(self) -> None:
        """Só para consistência de padrão: o orquestrador atômico compartilha uma Session
        e fará um único commit no fim, portanto não deve chamar este método.
        """
        self._db.rollback()
