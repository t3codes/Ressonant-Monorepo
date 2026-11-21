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

    def _can_manage_columns(self, board: Board, user_id: str, actor_is_admin: bool) -> bool:
        if actor_is_admin:
            return True
        from app.modules.teams.dataproviders.repository import TeamRepository
        from app.modules.workspace.dataproviders.repository import WorkspaceRepository

        team_repo = TeamRepository(self._repo._db)
        ws_repo = WorkspaceRepository(self._repo._db)
        ws = ws_repo.get_by_id(board.workspace_id)
        ws_member = ws_repo.is_member(board.workspace_id, user_id) if ws else None
        if ws and (ws.owner_id == user_id or (ws_member and ws_member.role == "admin")):
            return True
        team = team_repo.get_by_id(board.team_id)
        member = team_repo.is_member(board.team_id, user_id)
        is_team_owner = team is not None and team.owner_id == user_id
        is_team_admin = member is not None and member.role == "admin"
        return is_team_owner or is_team_admin

    def _normalize_column_positions(self, board_id: str) -> list[BoardColumn]:
        cols = self._column_repo.list_by_board(board_id)
        for idx, col in enumerate(cols):
            col.position = idx
        return cols

    def create_column(self, board_id: str, payload: BoardColumnCreate, user_id: str, actor_is_admin: bool = False) -> BoardColumn:
        """Cria coluna. Shift em posições >= position; renumera sequencialmente."""
        board = self.get(board_id, user_id)
        if not self._can_manage_columns(board, user_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar colunas")
        cols = self._column_repo.list_by_board(board_id)
        pos = max(0, min(payload.position, len(cols)))
        for col in cols:
            if col.position >= pos:
                col.position += 1
        column = BoardColumn(
            board_id=board_id,
            name=payload.name,
            slug=payload.slug,
            position=pos,
            wip_limit=payload.wip_limit,
        )
        try:
            self._column_repo.add(column)
            self._column_repo.commit()
            # normalize to contiguous sequence
            self._normalize_column_positions(board_id)
            self._column_repo.commit()
        except Exception:
            self._column_repo.rollback()
            raise
        return self._column_repo.get_by_id(column.id) or column

    def update_column(self, board_id: str, column_id: str, payload, user_id: str, actor_is_admin: bool = False) -> BoardColumn:
        board = self.get(board_id, user_id)
        if not self._can_manage_columns(board, user_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar colunas")
        column = self._column_repo.get_by_id(column_id)
        if column is None or column.board_id != board_id:
            raise _not_found()
        if payload.name is not None:
            column.name = payload.name
        if payload.slug is not None:
            column.slug = payload.slug
        if payload.wip_limit is not None:
            column.wip_limit = payload.wip_limit
        try:
            self._column_repo.commit()
        except Exception:
            self._column_repo.rollback()
            raise
        return column

    def delete_column(self, board_id: str, column_id: str, user_id: str, actor_is_admin: bool = False) -> None:
        board = self.get(board_id, user_id)
        if not self._can_manage_columns(board, user_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar colunas")
        column = self._column_repo.get_by_id(column_id)
        if column is None or column.board_id != board_id:
            raise _not_found()
        cards_count = self._column_repo.count_cards(column_id)
        if cards_count > 0:
            raise _conflict("Não é possível excluir coluna com cards. Mova os cards antes.", "BOARD_COLUMN_NOT_EMPTY")
        try:
            self._column_repo.delete(column)
            self._normalize_column_positions(board_id)
            self._column_repo.commit()
        except Exception:
            self._column_repo.rollback()
            raise

    def reorder_columns(self, board_id: str, ordered_column_ids: list[str], user_id: str, actor_is_admin: bool = False) -> list[BoardColumn]:
        board = self.get(board_id, user_id)
        if not self._can_manage_columns(board, user_id, actor_is_admin):
            raise _forbidden("Sem permissão para gerenciar colunas")
        cols = self._column_repo.list_by_board(board_id)
        current_ids = [c.id for c in cols]
        if len(ordered_column_ids) != len(current_ids) or set(ordered_column_ids) != set(current_ids):
            raise _conflict("Reordenação deve incluir todas as colunas do board", "BOARD_COLUMN_REORDER_INVALID")
        by_id = {c.id: c for c in cols}
        try:
            for idx, cid in enumerate(ordered_column_ids):
                by_id[cid].position = idx
            self._column_repo.commit()
        except Exception:
            self._column_repo.rollback()
            raise
        return self._column_repo.list_by_board(board_id)
