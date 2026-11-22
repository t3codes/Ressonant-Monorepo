import uuid
from datetime import UTC, datetime

from app.modules.kanban_cards.domain.models import Card
from app.modules.organization.domain.models import OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent, WorkspaceManagementGrant
from sqlalchemy import select
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
