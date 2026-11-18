from app.common.exceptions import ConflictException
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.teams.schemas.dto import (
    TeamCreate,
    TeamMemberAdd,
    TeamUpdate,
)
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Team não encontrado", error_code="TEAM_NOT_FOUND"),
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

    def create(self, payload: TeamCreate, owner_id: str) -> Team:
        """Cria team. workspace_id vem do payload; owner_id vem do JWT."""
        # Valida que o usuário é membro do workspace
        from app.modules.workspace.dataproviders.repository import WorkspaceRepository

        ws_repo = WorkspaceRepository(self._repo._db)
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

    def add_member(self, team_id: str, payload: TeamMemberAdd, user_id: str) -> TeamMember:
        """Adiciona membro ao team (só owner ou admin)."""
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        member = self._repo.is_member(team_id, user_id)
        if team.owner_id != user_id and (member is None or member.role != "admin"):
            raise _forbidden("Somente o owner ou admin pode adicionar membros")
        if self._repo.is_member(team_id, payload.user_id):
            raise _forbidden("Usuário já é membro deste team")
        new_member = TeamMember(team_id=team_id, user_id=payload.user_id, role=payload.role)
        try:
            self._repo.add_member(new_member)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return new_member
