from app.common.exceptions import ConflictException
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.teams.schemas.dto import (
    TeamCreate,
    TeamMemberAdd,
    TeamMemberUpdate,
    TeamUpdate,
)
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Team não encontrado", error_code="TEAM_NOT_FOUND"),
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


class TeamService:
    def __init__(self, repository: TeamRepository) -> None:
        self._repo = repository

    def _user_repo(self) -> UserRepository:
        return UserRepository(self._repo._db)

    def _ws_repo(self) -> WorkspaceRepository:
        return WorkspaceRepository(self._repo._db)

    def _can_manage_team(self, team: Team, actor_id: str, actor_is_admin: bool) -> bool:
        if actor_is_admin or team.owner_id == actor_id:
            return True
        member = self._repo.is_member(team.id, actor_id)
        if member is not None and member.role == "admin":
            return True
        ws = self._ws_repo().get_by_id(team.workspace_id)
        if ws is None:
            return False
        if ws.owner_id == actor_id:
            return True
        ws_member = self._ws_repo().is_member(team.workspace_id, actor_id)
        return ws_member is not None and ws_member.role == "admin"

    def _resolve_target_user_id(self, payload: TeamMemberAdd) -> str:
        if payload.user_id:
            user = self._user_repo().get_by_id(payload.user_id)
            if user is None:
                raise _user_not_found()
            return user.id
        user = self._user_repo().get_by_email(str(payload.email).lower()) if payload.email else None
        if user is None:
            raise _user_not_found()
        return user.id

    def create(self, payload: TeamCreate, owner_id: str) -> Team:
        """Cria team. workspace_id vem do payload; owner_id vem do JWT."""
        ws_repo = self._ws_repo()
        if not ws_repo.is_member(payload.workspace_id, owner_id):
            raise _forbidden("Você não é membro deste workspace")

        if self._repo.exists_by_slug(payload.slug):
            raise _conflict("Já existe um team com este slug", "TEAM_ALREADY_EXISTS")
        team = Team(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            workspace_id=payload.workspace_id,
            owner_id=owner_id,
        )
        try:
            self._repo.add(team)
            self._repo.add_member(TeamMember(team_id=team.id, user_id=owner_id, role="admin"))
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return team

    def get(self, team_id: str, user_id: str) -> Team:
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        if not self._repo.is_member(team_id, user_id):
            raise _forbidden("Você não é membro deste team")
        return team

    def list_for_workspace(
        self,
        workspace_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Team], int]:
        return self._repo.list_for_workspace(workspace_id, user_id, skip, limit, status_ativo)

    def update(self, team_id: str, payload: TeamUpdate, user_id: str) -> Team:
        team = self.get(team_id, user_id)
        member = self._repo.is_member(team_id, user_id)
        if team.owner_id != user_id and (member is None or member.role != "admin"):
            raise _forbidden("Somente o owner ou admin do team pode editar")
        if payload.name is not None:
            team.name = payload.name
        if payload.description is not None:
            team.description = payload.description
        if payload.status_ativo is not None:
            team.status_ativo = payload.status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return team

    def set_status(self, team_id: str, status_ativo: bool, user_id: str) -> Team:
        """Ativa/desativa team (só o owner)."""
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        if team.owner_id != user_id:
            raise _forbidden("Somente o owner pode ativar/desativar o team")
        team.status_ativo = status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return team

    def add_member(
        self, team_id: str, payload: TeamMemberAdd, actor_id: str, actor_is_admin: bool = False
    ) -> TeamMember:
        """Adiciona membro ao team (owner/admin do workspace, admin do time, ou interno_adm)."""
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        if not self._can_manage_team(team, actor_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar membros da equipe")
        target_id = self._resolve_target_user_id(payload)
        # alvo deve ser membro do workspace
        if self._ws_repo().is_member(team.workspace_id, target_id) is None:
            raise _forbidden("Usuário deve ser membro do workspace para entrar na equipe")
        if self._repo.is_member(team_id, target_id):
            raise _conflict("Usuário já é membro deste team", "TEAM_MEMBER_EXISTS")
        new_member = TeamMember(team_id=team_id, user_id=target_id, role=payload.role)
        try:
            self._repo.add_member(new_member)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return new_member

    def update_member(
        self,
        team_id: str,
        target_user_id: str,
        payload: TeamMemberUpdate,
        actor_id: str,
        actor_is_admin: bool = False,
    ) -> TeamMember:
        """Altera papel do membro na equipe."""
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        if not self._can_manage_team(team, actor_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar membros da equipe")
        member = self._repo.get_member(team_id, target_user_id)
        if member is None:
            raise _not_found()
        member.role = payload.role
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return member

    def list_members(self, team_id: str, user_id: str) -> list[TeamMember]:
        """Lista membros do team (só se o usuário é membro)."""
        self.get(team_id, user_id)
        return self._repo.list_members(team_id)
