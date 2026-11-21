from app.common.exceptions import ConflictException
from app.modules.kanban_boards.dataproviders.repository import (
    BoardColumnRepository,
    BoardRepository,
)
from app.modules.kanban_boards.domain.models import Board, BoardColumn
from app.modules.kanban_boards.schemas.dto import (
    BoardColumnCreate,
    BoardCreate,
    BoardUpdate,
)
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Board não encontrado", error_code="BOARD_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _forbidden(message: str) -> ForbiddenException:
    return ForbiddenException(
        ExceptionData(message=message, error_code="FORBIDDEN"), is_expected=True
    )


class BoardService:
    def __init__(
        self,
        repository: BoardRepository,
        column_repository: BoardColumnRepository,
    ) -> None:
        self._repo = repository
        self._column_repo = column_repository

    def _get_team_member(self, team_id: str, user_id: str):
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._repo._db)
        return team_repo, team_repo.is_member(team_id, user_id)

    def _require_board_editor(self, team_id: str, user_id: str) -> None:
        _, member = self._get_team_member(team_id, user_id)
        if member is None:
            raise _forbidden("Você não é membro deste time")
        if member.role == "viewer":
            raise _forbidden("Usuário com papel viewer não pode editar boards")

    def create(self, payload: BoardCreate, owner_id: str) -> Board:
        """Cria board. workspace_id e team_id vêm do payload; owner_id do JWT."""
        # Valida que o usuário é membro do time e não é viewer
        self._require_board_editor(payload.team_id, owner_id)

        if self._repo.exists_by_slug(payload.slug):
            raise _conflict("Já existe um board com este slug", "BOARD_ALREADY_EXISTS")
        board = Board(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            workspace_id=payload.workspace_id,
            team_id=payload.team_id,
        )
        try:
            self._repo.add(board)
            # Cria colunas padrão
            default_columns = [
                ("Backlog", "backlog", 0),
                ("Em Andamento", "em-andamento", 1),
                ("Feito", "feito", 2),
            ]
            for col_name, col_slug, col_position in default_columns:
                column = BoardColumn(
                    board_id=board.id,
                    name=col_name,
                    slug=col_slug,
                    position=col_position,
                )
                self._column_repo.add(column)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return board

    def get(self, board_id: str, user_id: str) -> Board:
        board = self._repo.get_by_id(board_id)
        if board is None:
            raise _not_found()
        if not self._repo.is_team_member(board_id, user_id):
            raise _forbidden("Você não é membro do time deste board")
        return board

    def list_for_workspace(
        self,
        workspace_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Board], int]:
        return self._repo.list_for_workspace(workspace_id, user_id, skip, limit, status_ativo)

    def update(self, board_id: str, payload: BoardUpdate, user_id: str) -> Board:
        board = self.get(board_id, user_id)
        self._require_board_editor(board.team_id, user_id)
        if payload.name is not None:
            board.name = payload.name
        if payload.description is not None:
            board.description = payload.description
        if payload.status_ativo is not None:
            board.status_ativo = payload.status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return board

    def set_status(self, board_id: str, status_ativo: bool, user_id: str) -> Board:
        """Ativa/desativa board (owner do time ou admin do time)."""
        board = self._repo.get_by_id(board_id)
        if board is None:
            raise _not_found()
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._repo._db)
        team = team_repo.get_by_id(board.team_id)
        member = team_repo.is_member(board.team_id, user_id)
        if member is None and (team is None or team.owner_id != user_id):
            raise _forbidden("Somente membros do time podem modificar o board")
        is_team_owner = team is not None and team.owner_id == user_id
        is_team_admin = member is not None and member.role == "admin"
        if not (is_team_owner or is_team_admin):
            raise _forbidden("Somente owner ou admin do time pode ativar/desativar o board")
        board.status_ativo = status_ativo
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return board

    def list_columns(self, board_id: str, user_id: str) -> list[BoardColumn]:
        """Lista colunas de um board (só se o usuário é membro do time)."""
        self.get(board_id, user_id)
        return self._column_repo.list_by_board(board_id)

    def create_column(self, board_id: str, payload: BoardColumnCreate, user_id: str) -> BoardColumn:
        """Cria uma coluna no board (owner ou admin do time)."""
        board = self.get(board_id, user_id)
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._repo._db)
        team = team_repo.get_by_id(board.team_id)
        member = team_repo.is_member(board.team_id, user_id)
        is_team_owner = team is not None and team.owner_id == user_id
        is_team_admin = member is not None and member.role == "admin"
        if not (is_team_owner or is_team_admin):
            raise _forbidden("Somente owner ou admin do time pode criar colunas")
        column = BoardColumn(
            board_id=board_id,
            name=payload.name,
            slug=payload.slug,
            position=payload.position,
            wip_limit=payload.wip_limit,
        )
        try:
            self._column_repo.add(column)
            self._column_repo.commit()
        except Exception:
            self._column_repo.rollback()
            raise
        return column
