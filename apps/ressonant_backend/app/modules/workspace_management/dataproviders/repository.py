import uuid
from datetime import UTC, datetime

from app.modules.kanban_cards.domain.models import Card
from app.modules.organization.domain.models import OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import (
    AuditEvent,
    CardTaxonomyModel,
    WorkspaceCapabilityGrant,
    WorkspaceManagementGrant,
    WorkspaceTaxonomyGrantModel,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session


class WorkspaceManagementRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except Exception:
            return False

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        if not self._is_uuid(workspace_id):
            return None
        return self._db.get(Workspace, workspace_id)

    def get_user(self, user_id: str) -> User | None:
        if not self._is_uuid(user_id):
            return None
        return self._db.get(User, user_id)

    def actor_has_inherent_access(self, workspace_id: str, user_id: str) -> bool:
        """Espelha ManagementAccess.has_inherent_access para os helpers de veto de domínio."""
        workspace = self.get_workspace(workspace_id)
        user = self.get_user(user_id)
        if workspace is None or user is None:
            return False
        return bool(
            workspace.owner_id == user_id
            or user.interno_adm
            or self.get_organization_role(workspace.organization_id or "", user_id)
            in {"owner", "billing_owner"}
        )

    def get_workspace_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    def get_organization_role(self, organization_id: str, user_id: str) -> str | None:
        """Papel ativo na organização, injetado no serviço de gestão (não vem de interno_adm)."""
        if not self._is_uuid(organization_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(OrganizationMember.role).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.status == "active",
            )
        )

    def get_active_grant(self, workspace_id: str, user_id: str) -> WorkspaceManagementGrant | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(WorkspaceManagementGrant).where(
                WorkspaceManagementGrant.workspace_id == workspace_id,
                WorkspaceManagementGrant.user_id == user_id,
                WorkspaceManagementGrant.revoked_at.is_(None),
            )
        )

    def list_active_grants(self, workspace_id: str) -> list[WorkspaceManagementGrant]:
        if not self._is_uuid(workspace_id):
            return []
        return list(
            self._db.scalars(
                select(WorkspaceManagementGrant)
                .where(
                    WorkspaceManagementGrant.workspace_id == workspace_id,
                    WorkspaceManagementGrant.revoked_at.is_(None),
                )
                .order_by(WorkspaceManagementGrant.created_at)
            )
        )

    def list_active_capability_overrides(self, workspace_id: str, user_id: str) -> dict[str, str]:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return {}
        rows = self._db.scalars(
            select(WorkspaceCapabilityGrant)
            .where(
                WorkspaceCapabilityGrant.workspace_id == workspace_id,
                WorkspaceCapabilityGrant.user_id == user_id,
                WorkspaceCapabilityGrant.revoked_at.is_(None),
            )
            .order_by(WorkspaceCapabilityGrant.capability)
        ).all()
        return {row.capability: row.effect for row in rows}

    def get_active_capability_override(
        self, workspace_id: str, user_id: str, capability: str
    ) -> WorkspaceCapabilityGrant | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id) or not capability:
            return None
        return self._db.scalar(
            select(WorkspaceCapabilityGrant).where(
                WorkspaceCapabilityGrant.workspace_id == workspace_id,
                WorkspaceCapabilityGrant.user_id == user_id,
                WorkspaceCapabilityGrant.capability == capability,
                WorkspaceCapabilityGrant.revoked_at.is_(None),
            )
        )

    def add_capability_override(self, grant: WorkspaceCapabilityGrant) -> WorkspaceCapabilityGrant:
        self._db.add(grant)
        self._db.flush()
        return grant

    def revoke_capability_override(
        self, grant: WorkspaceCapabilityGrant, *, revoked_by_id: str
    ) -> WorkspaceCapabilityGrant:
        grant.revoked_at = datetime.now(UTC)
        grant.revoked_by_id = revoked_by_id
        grant.revoke_reason = None
        grant.updated_at = datetime.now(UTC)
        self._db.flush()
        return grant

    def add_grant(self, grant: WorkspaceManagementGrant) -> WorkspaceManagementGrant:
        self._db.add(grant)
        self._db.flush()
        return grant

    def revoke_grant(
        self, grant: WorkspaceManagementGrant, *, revoked_by_id: str, revoke_reason: str | None
    ) -> WorkspaceManagementGrant:
        grant.revoked_at = datetime.now(UTC)
        grant.revoked_by_id = revoked_by_id
        grant.revoke_reason = revoke_reason
        grant.updated_at = datetime.now(UTC)
        self._db.flush()
        return grant

    def bump_permission_version(self, workspace_id: str) -> int:
        ws = self.get_workspace(workspace_id)
        if not ws:
            return 0
        ws.management_permission_version = int(ws.management_permission_version or 1) + 1
        self._db.flush()
        return ws.management_permission_version

    def bump_permission_version_atomic(self, workspace_id: str) -> int:
        """UPDATE ... RETURNING evita lost-update entre administradores concorrentes."""
        if not self._is_uuid(workspace_id):
            return 0
        result = self._db.execute(
            update(Workspace)
            .where(Workspace.id == workspace_id)
            .values(management_permission_version=Workspace.management_permission_version + 1)
            .returning(Workspace.management_permission_version),
            execution_options={"synchronize_session": "fetch"},
        )
        version = result.scalar_one_or_none()
        return int(version or 0)

    # Audit: append-only
    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def list_audit_events(
        self, workspace_id: str, *, skip: int = 0, limit: int = 50
    ) -> list[AuditEvent]:
        if not self._is_uuid(workspace_id):
            return []
        return list(
            self._db.scalars(
                select(AuditEvent)
                .where(AuditEvent.workspace_id == workspace_id)
                .order_by(AuditEvent.occurred_at.desc())
                .offset(skip)
                .limit(limit)
            )
        )

    def get_active_taxonomy_grant(
        self, workspace_id: str, user_id: str
    ) -> WorkspaceTaxonomyGrantModel | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(WorkspaceTaxonomyGrantModel).where(
                WorkspaceTaxonomyGrantModel.workspace_id == workspace_id,
                WorkspaceTaxonomyGrantModel.user_id == user_id,
                WorkspaceTaxonomyGrantModel.revoked_at.is_(None),
            )
        )

    def list_active_taxonomy_grants(self, workspace_id: str) -> list[WorkspaceTaxonomyGrantModel]:
        if not self._is_uuid(workspace_id):
            return []
        return list(
            self._db.scalars(
                select(WorkspaceTaxonomyGrantModel)
                .where(
                    WorkspaceTaxonomyGrantModel.workspace_id == workspace_id,
                    WorkspaceTaxonomyGrantModel.revoked_at.is_(None),
                )
                .order_by(WorkspaceTaxonomyGrantModel.created_at)
            )
        )

    def add_taxonomy_grant(self, grant: WorkspaceTaxonomyGrantModel) -> WorkspaceTaxonomyGrantModel:
        self._db.add(grant)
        self._db.flush()
        return grant

    def revoke_taxonomy_grant(
        self,
        grant: WorkspaceTaxonomyGrantModel,
        *,
        revoked_by_id: str,
        revoke_reason: str | None,
    ) -> WorkspaceTaxonomyGrantModel:
        grant.revoked_at = datetime.now(UTC)
        grant.revoked_by_id = revoked_by_id
        grant.revoke_reason = revoke_reason
        grant.updated_at = datetime.now(UTC)
        self._db.flush()
        return grant

    def list_taxonomy(
        self, workspace_id: str, *, kind: str, include_inactive: bool
    ) -> list[CardTaxonomyModel]:
        if not self._is_uuid(workspace_id):
            return []
        stmt = select(CardTaxonomyModel).where(
            CardTaxonomyModel.workspace_id == workspace_id,
            CardTaxonomyModel.kind == kind,
        )
        if not include_inactive:
            stmt = stmt.where(CardTaxonomyModel.desativado_em.is_(None))
        return list(self._db.scalars(stmt.order_by(CardTaxonomyModel.name)))

    def get_taxonomy(self, workspace_id: str, taxonomy_id: str) -> CardTaxonomyModel | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(taxonomy_id):
            return None
        return self._db.scalar(
            select(CardTaxonomyModel).where(
                CardTaxonomyModel.workspace_id == workspace_id,
                CardTaxonomyModel.id == taxonomy_id,
            )
        )

    def add_taxonomy(self, item: CardTaxonomyModel) -> CardTaxonomyModel:
        self._db.add(item)
        self._db.flush()
        return item

    def deactivate_taxonomy(
        self, item: CardTaxonomyModel, *, deactivated_by_id: str, reason: str | None
    ) -> CardTaxonomyModel:
        item.desativado_em = datetime.now(UTC)
        item.desativado_by_id = deactivated_by_id
        item.deactivate_reason = reason
        self._db.flush()
        return item

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def list_workspace_members(self, workspace_id: str) -> list[dict]:
        if not self._is_uuid(workspace_id):
            return []
        rows = self._db.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.criado_em)
        ).all()
        return [
            {
                "user_id": m.user_id,
                "role": m.role,
                "criado_em": m.criado_em,
                "name": u.name,
                "email": u.email,
            }
            for m, u in rows
        ]

    def get_workspace_person(self, workspace_id: str, user_id: str) -> dict | None:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return None
        row = self._db.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).first()
        if row is None:
            return None
        member, user = row
        team_rows = self._db.execute(
            select(Team, TeamMember)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.workspace_id == workspace_id,
                Team.is_deleted.is_(False),
                TeamMember.user_id == user_id,
            )
            .order_by(Team.criado_em, Team.id)
        ).all()
        return {
            "user_id": member.user_id,
            "role": member.role,
            "criado_em": member.criado_em,
            "name": user.name,
            "email": user.email,
            "teams": [
                {"team_id": team.id, "team_name": team.name, "team_role": team_member.role}
                for team, team_member in team_rows
            ],
        }

    def get_team(self, team_id: str) -> Team | None:
        if not self._is_uuid(team_id):
            return None
        return self._db.get(Team, team_id)

    def get_team_member(self, team_id: str, user_id: str) -> TeamMember | None:
        if not self._is_uuid(team_id) or not self._is_uuid(user_id):
            return None
        return self._db.scalar(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )

    def add_team_member(self, member: TeamMember) -> TeamMember:
        self._db.add(member)
        self._db.flush()
        return member

    def remove_team_member(self, member: TeamMember) -> None:
        self._db.delete(member)
        self._db.flush()

    def remove_workspace_member(self, member: WorkspaceMember) -> None:
        self._db.delete(member)
        self._db.flush()

    def list_workspace_team_memberships(self, workspace_id: str, user_id: str) -> list[TeamMember]:
        if not self._is_uuid(workspace_id) or not self._is_uuid(user_id):
            return []
        return list(
            self._db.scalars(
                select(TeamMember)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.workspace_id == workspace_id, TeamMember.user_id == user_id)
            )
        )

    def list_teams(self, workspace_id: str, include_deleted: bool = False) -> list[Team]:
        if not self._is_uuid(workspace_id):
            return []
        stmt = select(Team).where(Team.workspace_id == workspace_id)
        if not include_deleted:
            stmt = stmt.where(Team.is_deleted.is_(False))
        return list(self._db.scalars(stmt.order_by(Team.criado_em)))

    def count_team_members(self, team_id: str) -> int:
        from sqlalchemy import func

        return int(
            self._db.scalar(
                select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id)
            )
            or 0
        )

    def list_blocked_cards(self, workspace_id: str) -> list[Card]:
        if not self._is_uuid(workspace_id):
            return []
        # cards in boards/teams belonging to workspace; easiest join via Team
        stmt = (
            select(Card)
            .join(Team, Team.id == Card.team_id)
            .where(
                Team.workspace_id == workspace_id,
                Card.is_blocked.is_(True),
                Card.status_ativo.is_(True),
            )
            .order_by(Card.blocked_at.desc().nullslast())
        )
        return list(self._db.scalars(stmt))
