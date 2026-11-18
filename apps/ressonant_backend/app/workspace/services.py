from common.errors import ExceptionData, ForbiddenException, NotFoundException

from app.common.exceptions import ConflictException
from app.workspace.models import Workspace, WorkspaceMember
from app.workspace.repository import WorkspaceRepository
from app.workspace.schemas import WorkspaceCreate, WorkspaceMemberAdd, WorkspaceUpdate


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Workspace não encontrado", error_code="WORKSPACE_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _forbidden(message: str) -> ForbiddenException:
    return ForbiddenException(
        ExceptionData(message=message, error_code="FORBIDDEN"), is_expected=True
    )


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repo = repository

    def create(self, payload: WorkspaceCreate, owner_id: str) -> Workspace:
        """Cria workspace. owner_id vem do JWT, nunca do payload."""
        if self._repo.exists_by_slug(payload.slug):
            raise _conflict("Já existe um workspace com este slug", "WORKSPACE_ALREADY_EXISTS")
        workspace = Workspace(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            owner_id=owner_id,
        )
        try:
            self._repo.add(workspace)
            # O dono entra automaticamente como admin
            self._repo.add_member(
                WorkspaceMember(workspace_id=workspace.id, user_id=owner_id, role="admin")
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return workspace

    def get(self, workspace_id: str, user_id: str) -> Workspace:
        workspace = self._repo.get_by_id(workspace_id)
        if workspace is None:
            raise _not_found()
        if not self._repo.is_member(workspace_id, user_id):
            raise _forbidden("Você não é membro deste workspace")
        return workspace

    def list_for_user(
        self, user_id: str, skip: int = 0, limit: int = 50, status_ativo: bool | None = None
    ) -> tuple[list[Workspace], int]:
        return self._repo.list_for_user(user_id, skip, limit, status_ativo)

    def update(self, workspace_id: str, payload: WorkspaceUpdate, user_id: str) -> Workspace:
        workspace = self.get(workspace_id, user_id)
        # Somente owner ou admin do workspace pode editar
        member = self._repo.is_member(workspace_id, user_id)
        if workspace.owner_id != user_id and (member is None or member.role != "admin"):
            raise _forbidden("Somente o owner ou admin do workspace pode editar")
        if payload.name is not None:
            workspace.name = payload.name
        if payload.description is not None:
            workspace.description = payload.description
        if payload.status_ativo is not None:
            workspace.status_ativo = payload.status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return workspace

    def set_status(self, workspace_id: str, status_ativo: bool, user_id: str) -> Workspace:
        """Ativa/desativa workspace (só o owner)."""
        workspace = self._repo.get_by_id(workspace_id)
        if workspace is None:
            raise _not_found()
        if workspace.owner_id != user_id:
            raise _forbidden("Somente o owner pode ativar/desativar o workspace")
        workspace.status_ativo = status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return workspace

    def add_member(
        self, workspace_id: str, payload: WorkspaceMemberAdd, user_id: str
    ) -> WorkspaceMember:
        """Adiciona membro ao workspace (só owner ou admin)."""
        workspace = self._repo.get_by_id(workspace_id)
        if workspace is None:
            raise _not_found()
        member = self._repo.is_member(workspace_id, user_id)
        if workspace.owner_id != user_id and (member is None or member.role != "admin"):
            raise _forbidden("Somente o owner ou admin pode adicionar membros")
        if self._repo.is_member(workspace_id, payload.user_id):
            raise _forbidden("Usuário já é membro deste workspace")
        new_member = WorkspaceMember(
            workspace_id=workspace_id, user_id=payload.user_id, role=payload.role
        )
        try:
            self._repo.add_member(new_member)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return new_member
