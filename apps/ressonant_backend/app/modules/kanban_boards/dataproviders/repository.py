import uuid

from app.modules.kanban_boards.domain.models import Board, BoardColumn
from app.modules.teams.domain.models import Team, TeamMember
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


class BoardRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, board_id: str) -> Board | None:
        try:
            uuid.UUID(board_id)
        except ValueError:
            return None
        return self._db.get(Board, board_id)

    def get_by_slug(self, slug: str) -> Board | None:
        return self._db.scalar(select(Board).where(Board.slug == slug))

    def exists_by_slug(self, slug: str) -> bool:
        return self._db.scalar(select(Board.id).where(Board.slug == slug).limit(1)) is not None

    def list_for_workspace(
        self,
        workspace_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Board], int]:
        """Boards de um workspace onde o usuário é membro do time."""
        try:
            uuid.UUID(workspace_id)
            uuid.UUID(user_id)
        except ValueError:
            return [], 0
        stmt = (
            select(Board)
            .join(Team, Team.id == Board.team_id)
            .join(TeamMember, TeamMember.team_id == Team.id, isouter=True)
            .where(Board.workspace_id == workspace_id)
            .where(or_(Team.owner_id == user_id, TeamMember.user_id == user_id))
            .distinct()
        )
        if status_ativo is not None:
            stmt = stmt.where(Board.status_ativo == status_ativo)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(stmt.order_by(Board.criado_em, Board.id).offset(skip).limit(limit))
        return list(items), total

    def is_team_member(self, board_id: str, user_id: str) -> bool:
        """Verifica se o usuário é membro do time do board."""
        try:
            uuid.UUID(board_id)
            uuid.UUID(user_id)
        except ValueError:
            return False
        board = self._db.get(Board, board_id)
        if board is None:
            return False
        # Verificar se o usuário é membro do time (precisa do TeamRepository)
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._db)
        return team_repo.is_member(board.team_id, user_id) is not None

    def add(self, board: Board) -> Board:
        self._db.add(board)
        self._db.flush()
        return board

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()


class BoardColumnRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, column_id: str) -> BoardColumn | None:
        try:
            uuid.UUID(column_id)
        except ValueError:
            return None
        return self._db.get(BoardColumn, column_id)

    def list_by_board(self, board_id: str) -> list[BoardColumn]:
        return list(
            self._db.scalars(
                select(BoardColumn)
                .where(BoardColumn.board_id == board_id)
                .order_by(BoardColumn.position, BoardColumn.created_at)
            ).all()
        )

    def count_cards(self, column_id: str) -> int:
        from app.modules.kanban_cards.domain.models import Card

        return (
            self._db.scalar(
                select(func.count()).select_from(Card).where(Card.column_id == column_id)
            )
            or 0
        )

    def add(self, column: BoardColumn) -> BoardColumn:
        self._db.add(column)
        self._db.flush()
        return column

    def delete(self, column: BoardColumn) -> None:
        self._db.delete(column)
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
