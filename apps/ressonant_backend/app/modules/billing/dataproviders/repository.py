import uuid

from app.modules.billing.domain.models import ACTIVE_SUBSCRIPTION_STATUSES, Plan, Subscription
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
from sqlalchemy import select
from sqlalchemy.orm import Session


class BillingRepository:
    """Única camada que fala com a Session do módulo de billing."""

    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except Exception:
            return False

    def get_organization(self, organization_id: str) -> Organization | None:
        if not self._is_uuid(organization_id):
            return None
        return self._db.get(Organization, organization_id)

    def get_organization_role(self, organization_id: str, user_id: str) -> str | None:
        """Papel organizacional ativo, injetado de fora do módulo de gestão."""
        if not self._is_uuid(organization_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(OrganizationMember.role).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.status == "active",
            )
        )

    def count_seats_used(self, organization_id: str) -> int:
        """União de membros ativos da organização e membros de seus workspaces."""
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

    def get_plan_by_code(self, code: str) -> Plan | None:
        return self._db.scalar(select(Plan).where(Plan.code == code, Plan.active.is_(True)))

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

    def get_subscription_for_display(
        self, organization_id: str
    ) -> tuple[Subscription, Plan] | None:
        """Inclui canceladas para que o último estado continue legível no contrato."""
        if not self._is_uuid(organization_id):
            return None
        row = self._db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.organization_id == organization_id)
            .order_by(Subscription.criado_em.desc(), Subscription.id.desc())
            .limit(1)
        ).first()
        return (row[0], row[1]) if row is not None else None

    def permission_version_for_organization(self, organization_id: str) -> int:
        if not self._is_uuid(organization_id):
            return 1
        versions = self._db.scalars(
            select(Workspace.management_permission_version).where(
                Workspace.organization_id == organization_id
            )
        )
        return max((int(version or 1) for version in versions), default=1)

    def add_subscription(self, subscription: Subscription) -> Subscription:
        self._db.add(subscription)
        self._db.flush()
        return subscription

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def list_audit_events(
        self, organization_id: str, *, action: str | None = None
    ) -> list[AuditEvent]:
        if not self._is_uuid(organization_id):
            return []
        statement = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        return list(self._db.scalars(statement.order_by(AuditEvent.occurred_at, AuditEvent.id)))

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
