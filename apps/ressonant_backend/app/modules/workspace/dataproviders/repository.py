import uuid

from app.modules.organization.domain.models import OrganizationMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


class WorkspaceRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, workspace_id: str) -> Workspace | None:
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return None
        return self._db.get(Workspace, workspace_id)

    def get_by_slug(self, slug: str) -> Workspace | None:
        return self._db.scalar(select(Workspace).where(Workspace.slug == slug))

    def exists_by_slug(self, slug: str) -> bool:
        return (
            self._db.scalar(select(Workspace.id).where(Workspace.slug == slug).limit(1)) is not None
        )

    def list_eligible_organization_ids(self, user_id: str) -> list[str]:
        """Ids das organizações com membership ativa do ator como owner/admin."""
        return list(
            self._db.scalars(
                select(OrganizationMember.organization_id)
                .where(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.status == "active",
                    OrganizationMember.role.in_(("owner", "admin")),
                )
                .distinct()
                .order_by(OrganizationMember.organization_id)
            )
        )

    def list_for_user(
        self, user_id: str, skip: int = 0, limit: int = 50, status_ativo: bool | None = None
    ) -> tuple[list[Workspace], int]:
        """Workspaces onde o usuário é dono ou membro."""
        try:
            uuid.UUID(user_id)
        except ValueError:
            return [], 0
        stmt = (
            select(Workspace)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.id,
                isouter=True,
            )
            .where(or_(Workspace.owner_id == user_id, WorkspaceMember.user_id == user_id))
            .distinct()
        )
        if status_ativo is not None:
            stmt = stmt.where(Workspace.status_ativo == status_ativo)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(Workspace.criado_em, Workspace.id).offset(skip).limit(limit)
        )
        return list(items), total

    def is_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        try:
            uuid.UUID(workspace_id)
            uuid.UUID(user_id)
        except ValueError:
            return None
        return self._db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    def add(self, workspace: Workspace) -> Workspace:
        self._db.add(workspace)
        self._db.flush()
        return workspace

    def add_member(self, member: WorkspaceMember) -> WorkspaceMember:
        self._db.add(member)
        self._db.flush()
        return member

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        return self.is_member(workspace_id, user_id)

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return []
        return list(
            self._db.scalars(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(WorkspaceMember.criado_em)
            )
        )

    def remove_member(self, member: WorkspaceMember) -> None:
        self._db.delete(member)
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
