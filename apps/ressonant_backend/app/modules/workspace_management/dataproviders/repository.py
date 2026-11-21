import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.kanban_cards.domain.models import Card
from app.modules.workspace_management.domain.models import AuditEvent, WorkspaceManagementGrant


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

    def revoke_grant(self, grant: WorkspaceManagementGrant, *, revoked_by_id: str, revoke_reason: str | None) -> WorkspaceManagementGrant:
        grant.revoked_at = datetime.now(timezone.utc)
        grant.revoked_by_id = revoked_by_id
        grant.revoke_reason = revoke_reason
        grant.updated_at = datetime.now(timezone.utc)
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

    def list_audit_events(self, workspace_id: str, *, skip: int = 0, limit: int = 50) -> list[AuditEvent]:
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


    def list_workspace_members(self, workspace_id: str) -> list[WorkspaceMember]:
        if not self._is_uuid(workspace_id):
            return []
        return list(self._db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id).order_by(WorkspaceMember.criado_em)))

    def list_teams(self, workspace_id: str, include_deleted: bool = False) -> list[Team]:
        if not self._is_uuid(workspace_id):
            return []
        stmt = select(Team).where(Team.workspace_id == workspace_id)
        if not include_deleted:
            stmt = stmt.where(Team.is_deleted.is_(False))
        return list(self._db.scalars(stmt.order_by(Team.criado_em)))

    def count_team_members(self, team_id: str) -> int:
        from sqlalchemy import func
        return int(self._db.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id)) or 0)

    def list_blocked_cards(self, workspace_id: str) -> list[Card]:
        if not self._is_uuid(workspace_id):
            return []
        # cards in boards/teams belonging to workspace; easiest join via Team
        stmt = (
            select(Card)
            .join(Team, Team.id == Card.team_id)
            .where(Team.workspace_id == workspace_id, Card.is_blocked.is_(True), Card.status_ativo.is_(True))
            .order_by(Card.blocked_at.desc().nullslast())
        )
        return list(self._db.scalars(stmt))
