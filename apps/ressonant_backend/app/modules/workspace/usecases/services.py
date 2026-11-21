from app.common.exceptions import ConflictException
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace.schemas.dto import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Workspace não encontrado", error_code="WORKSPACE_NOT_FOUND"),
        is_expected=True,
    )


def _user_not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Usuário não encontrado", error_code="USER_NOT_FOUND"),
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

    def _get_user_repo(self) -> UserRepository:
        return UserRepository(self._repo._db)

    def _require_workspace(self, workspace_id: str) -> Workspace:
        workspace = self._repo.get_by_id(workspace_id)
        if workspace is None:
            raise _not_found()
        return workspace

    def _is_workspace_admin_or_owner(self, workspace: Workspace, actor_id: str, actor_is_admin: bool) -> bool:
        if actor_is_admin or workspace.owner_id == actor_id:
            return True
        member = self._repo.is_member(workspace.id, actor_id)
        return member is not None and member.role == "admin"

    def _resolve_target_user_id(self, payload: WorkspaceMemberAdd) -> str:
        if payload.user_id:
            user = self._get_user_repo().get_by_id(payload.user_id)
            if user is None:
                raise _user_not_found()
            return user.id
        # busca por e-mail exato, sem listar usuários
        user = self._get_user_repo().get_by_email(str(payload.email).lower()) if payload.email else None
        if user is None:
            raise _user_not_found()
        return user.id

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

    def list_members(self, workspace_id: str, actor_id: str) -> list[WorkspaceMember]:
        workspace = self._require_workspace(workspace_id)
        if not self._repo.is_member(workspace_id, actor_id):
            raise _forbidden("Você não é membro deste workspace")
        return self._repo.list_members(workspace_id)

    def add_member(
        self, workspace_id: str, payload: WorkspaceMemberAdd, actor_id: str, actor_is_admin: bool = False
    ) -> WorkspaceMember:
        """Adiciona membro ao workspace (owner/admin do workspace ou interno_adm)."""
        workspace = self._require_workspace(workspace_id)
        if not self._is_workspace_admin_or_owner(workspace, actor_id, actor_is_admin):
            raise _forbidden("Somente o owner ou admin do workspace pode adicionar membros")
        target_id = self._resolve_target_user_id(payload)
        if self._repo.is_member(workspace_id, target_id):
            raise _conflict("Usuário já é membro deste workspace", "WORKSPACE_MEMBER_EXISTS")
        new_member = WorkspaceMember(workspace_id=workspace_id, user_id=target_id, role=payload.role)
        try:
            self._repo.add_member(new_member)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return new_member

    def update_member(
        self,
        workspace_id: str,
        target_user_id: str,
        payload: WorkspaceMemberUpdate,
        actor_id: str,
        actor_is_admin: bool = False,
    ) -> WorkspaceMember:
        """Altera papel do membro. Só owner do workspace ou interno_adm."""
        workspace = self._require_workspace(workspace_id)
        if not (actor_is_admin or workspace.owner_id == actor_id):
            raise _forbidden("Somente o owner do workspace pode alterar permissões")
        if payload.role == "owner":
            self.transfer_owner(workspace_id, target_user_id, actor_id, actor_is_admin)
            member = self._repo.get_member(workspace_id, target_user_id)
            if member is None:
                raise _not_found()
            return member
        member = self._repo.get_member(workspace_id, target_user_id)
        if member is None:
            raise _not_found()
        # owner atual não é rebaixado via membership
        if target_user_id == workspace.owner_id and payload.role != "admin":
            raise _forbidden("O owner deve permanecer com acesso administrativo")
        member.role = payload.role
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return member

    def transfer_owner(
        self, workspace_id: str, new_owner_user_id: str, actor_id: str, actor_is_admin: bool = False
    ) -> Workspace:
        """Transfere propriedade do workspace. Só owner do workspace ou interno_adm."""
        workspace = self._require_workspace(workspace_id)
        if not (actor_is_admin or workspace.owner_id == actor_id):
            raise _forbidden("Somente o owner do workspace pode transferir a propriedade")
        if new_owner_user_id == workspace.owner_id:
            return workspace
        new_owner_member = self._repo.get_member(workspace_id, new_owner_user_id)
        if new_owner_member is None:
            raise _conflict("Novo owner deve ser membro do workspace", "WORKSPACE_MEMBER_NOT_FOUND")
        old_owner_id = workspace.owner_id
        try:
            workspace.owner_id = new_owner_user_id
            new_owner_member.role = "admin"
            old_member = self._repo.get_member(workspace_id, old_owner_id)
            if old_member is not None and old_member.role != "admin":
                old_member.role = "admin"
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return workspace
