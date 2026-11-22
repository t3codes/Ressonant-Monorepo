import re
from datetime import UTC, datetime

from app.common.exceptions import ConflictException
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.teams.schemas.dto import (
    TeamCreate,
    TeamMemberAdd,
    TeamMemberUpdate,
    TeamSoftDeleteInput,
    TeamUpdate,
)
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from common.errors import ExceptionData, ForbiddenException, NotFoundException
from sqlalchemy.exc import IntegrityError


def derive_key_prefix(slug: str) -> str:
    """Mesma base da migration 0015: alfanumérico, uppercase, até 20 chars."""
    return re.sub(r"[^A-Za-z0-9]", "", slug).upper()[:20] or "TEAM"


def allocate_key_prefix(slug: str, used: set[str]) -> str:
    """Mesmo sufixo da migration 0015: base, base2, base3... limitado a 20 chars."""
    base = derive_key_prefix(slug)
    prefix = base
    counter = 2
    while prefix in used:
        suffix = str(counter)
        prefix = base[: 20 - len(suffix)] + suffix
        counter += 1
    return prefix


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
        used = self._repo.list_key_prefixes(payload.workspace_id)
        team = Team(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            workspace_id=payload.workspace_id,
            owner_id=owner_id,
            key_prefix=allocate_key_prefix(payload.slug, used),
        )
        try:
            self._repo.add(team)
            self._repo.add_member(TeamMember(team_id=team.id, user_id=owner_id, role="admin"))
            self._repo.commit()
        except IntegrityError as exc:
            self._repo.rollback()
            raise _conflict(
                "Prefixo de chave do team já está em uso neste workspace",
                "TEAM_KEY_PREFIX_CONFLICT",
            ) from exc
        except Exception:
            self._repo.rollback()
            raise
        return team

    def get(self, team_id: str, user_id: str) -> Team:
        team = self._repo.get_by_id(team_id)
        if team is None or team.is_deleted:
            raise _not_found()
        if not self._repo.is_member(team_id, user_id) and team.owner_id != user_id:
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
        new_member = TeamMember(
            team_id=team_id,
            user_id=target_id,
            role=payload.role,
            can_retrocede=payload.can_retrocede,
        )
        try:
            self._repo.add_member(new_member)
            ws = self._ws_repo().get_by_id(team.workspace_id)
            if ws is not None:
                ws.management_permission_version = (
                    int(getattr(ws, "management_permission_version", 1) or 1) + 1
                )
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
        if payload.role is not None:
            member.role = payload.role
        if payload.can_retrocede is not None:
            member.can_retrocede = payload.can_retrocede
        try:
            ws = self._ws_repo().get_by_id(team.workspace_id)
            if ws is not None:
                ws.management_permission_version = (
                    int(getattr(ws, "management_permission_version", 1) or 1) + 1
                )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return member

    def list_members(self, team_id: str, user_id: str) -> list[TeamMember]:
        """Lista membros do team (só se o usuário é membro)."""
        self.get(team_id, user_id)
        return self._repo.list_members(team_id)

    def _require_workspace_owner_or_interno_adm(
        self, team: Team, actor_id: str, actor_is_interno_adm: bool
    ) -> None:
        if actor_is_interno_adm:
            return
        ws = self._ws_repo().get_by_id(team.workspace_id)
        if ws is None or ws.owner_id != actor_id:
            raise _forbidden("Apenas owner do workspace ou interno_adm pode executar esta ação")

    def soft_delete(
        self,
        team_id: str,
        payload: TeamSoftDeleteInput,
        actor_id: str,
        actor_is_interno_adm: bool = False,
    ) -> Team:
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        if team.is_deleted:
            raise _conflict("Equipe já está deletada", "TEAM_ALREADY_DELETED")
        self._require_workspace_owner_or_interno_adm(team, actor_id, actor_is_interno_adm)

        members = self._repo.list_members(team_id)
        reassign_map = {r.user_id: r.target_team_id for r in payload.member_reassignments}
        member_ids = {m.user_id for m in members}
        if set(reassign_map.keys()) != member_ids:
            missing = member_ids - set(reassign_map.keys())
            extra = set(reassign_map.keys()) - member_ids
            if missing or extra:
                raise _conflict(
                    "Reatribuição deve incluir todos os membros ativos da equipe",
                    "TEAM_MEMBER_REASSIGNMENT_REQUIRED",
                )

        # validate targets and reassign
        for m in members:
            target_team_id = reassign_map[m.user_id]
            if target_team_id == team_id:
                raise _conflict("Equipe de destino inválida", "TEAM_MEMBER_REASSIGNMENT_INVALID")
            target_team = self._repo.get_by_id(target_team_id)
            if target_team is None or target_team.workspace_id != team.workspace_id:
                raise _conflict("Equipe de destino inválida", "TEAM_MEMBER_REASSIGNMENT_INVALID")
            if target_team.is_deleted or not target_team.status_ativo:
                raise _conflict(
                    "Equipe de destino deve estar ativa", "TEAM_MEMBER_REASSIGNMENT_INVALID"
                )
            if self._ws_repo().is_member(team.workspace_id, m.user_id) is None:
                raise _conflict(
                    "Usuário deve ser membro do workspace", "TEAM_MEMBER_REASSIGNMENT_INVALID"
                )
            existing = self._repo.is_member(target_team_id, m.user_id)
            if existing is None:
                self._repo.add_member(
                    TeamMember(
                        team_id=target_team_id,
                        user_id=m.user_id,
                        role=m.role,
                        can_retrocede=m.can_retrocede,
                    )
                )
            self._repo.remove_member(m)

        team.is_deleted = True
        team.deleted_at = datetime.now(UTC)
        team.deleted_by = actor_id
        team.status_ativo = False
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return team

    def list_deleted(
        self, workspace_id: str, actor_id: str, actor_is_interno_adm: bool = False
    ) -> list[Team]:
        ws = self._ws_repo().get_by_id(workspace_id)
        if ws is None:
            raise NotFoundException(
                ExceptionData(message="Workspace não encontrado", error_code="WORKSPACE_NOT_FOUND"),
                is_expected=True,
            )
        if not actor_is_interno_adm and ws.owner_id != actor_id:
            raise _forbidden("Apenas owner do workspace ou interno_adm pode ver equipes deletadas")
        return self._repo.list_deleted_for_workspace(workspace_id)

    def permanent_delete(
        self, team_id: str, actor_id: str, actor_is_interno_adm: bool = False
    ) -> None:
        team = self._repo.get_by_id(team_id)
        if team is None:
            raise _not_found()
        self._require_workspace_owner_or_interno_adm(team, actor_id, actor_is_interno_adm)
        if not team.is_deleted:
            raise _conflict(
                "Equipe deve estar na lixeira antes da exclusão definitiva", "TEAM_NOT_SOFT_DELETED"
            )
        # block if boards still exist (safe default)
        from app.modules.kanban_boards.domain.models import Board

        has_board = (
            self._repo._db.query(Board.id).filter(Board.team_id == team_id).first() is not None
        )
        if has_board:
            raise _conflict(
                "Equipe possui boards vinculados. "
                "Remova dependências antes da exclusão definitiva.",
                "TEAM_HAS_DEPENDENCIES",
            )
        try:
            # remove leftover members just in case
            for m in self._repo.list_members(team_id):
                self._repo.remove_member(m)
            self._repo.delete_team(team)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
