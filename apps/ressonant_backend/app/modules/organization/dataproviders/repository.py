import uuid
from datetime import datetime

from app.modules.billing.domain.models import ACTIVE_SUBSCRIPTION_STATUSES, Plan, Subscription
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from sqlalchemy import select
from sqlalchemy.orm import Session


class OrganizationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

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

    def count_seats_used(self, organization_id: str) -> int:
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
        return len(organization_users | workspace_users)

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

    def get_invitation_by_id(self, invitation_id: str) -> Invitation | None:
        if not self._is_uuid(invitation_id):
            return None
        return self._db.get(Invitation, invitation_id)

    def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        return self._db.scalar(select(Invitation).where(Invitation.token_hash == token_hash))

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
        self._db.flush()

    def mark_invitation_revoked(self, invitation: Invitation, *, revoked_at: datetime) -> None:
        invitation.revoked_at = revoked_at
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
