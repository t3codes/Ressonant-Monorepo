from collections.abc import Collection

from app.modules.billing.domain.models import ACTIVE_SUBSCRIPTION_STATUSES, Plan, Subscription
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from sqlalchemy import select
from sqlalchemy.orm import Session


class ContextRepository:
    """Leituras do bootstrap; nenhuma decisão de autorização vive aqui."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_organization_memberships(
        self, user_id: str
    ) -> list[tuple[Organization, OrganizationMember]]:
        rows = self._db.execute(
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.criado_em, Organization.id)
        ).all()
        return [(organization, member) for organization, member in rows]

    def list_organizations_by_ids(
        self, organization_ids: Collection[str]
    ) -> dict[str, Organization]:
        if not organization_ids:
            return {}
        return {
            organization.id: organization
            for organization in self._db.scalars(
                select(Organization).where(Organization.id.in_(set(organization_ids)))
            )
        }

    def list_workspaces_for_user(self, user_id: str) -> list[tuple[Workspace, WorkspaceMember]]:
        rows = self._db.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.criado_em, Workspace.id)
        ).all()
        return [(workspace, member) for workspace, member in rows]

    def list_workspace_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return list(
            self._db.scalars(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(WorkspaceMember.criado_em, WorkspaceMember.id)
            )
        )

    def list_user_teams(self, workspace_id: str, user_id: str) -> list[tuple[Team, TeamMember]]:
        rows = self._db.execute(
            select(Team, TeamMember)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.workspace_id == workspace_id,
                TeamMember.user_id == user_id,
                Team.is_deleted.is_(False),
            )
            .order_by(Team.criado_em, Team.id)
        ).all()
        return [(team, member) for team, member in rows]

    def has_team_membership(self, user_id: str) -> bool:
        return (
            self._db.scalar(
                select(TeamMember.id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(TeamMember.user_id == user_id, Team.is_deleted.is_(False))
                .limit(1)
            )
            is not None
        )

    def get_active_subscription(self, organization_id: str) -> tuple[Subscription, Plan] | None:
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
