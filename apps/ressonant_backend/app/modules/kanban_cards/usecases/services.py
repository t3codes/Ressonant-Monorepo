from app.common.exceptions import ConflictException
from app.modules.kanban_boards.dataproviders.repository import BoardRepository
from app.modules.kanban_cards.dataproviders.repository import CardRepository
from app.modules.kanban_cards.domain.models import Card
from app.modules.kanban_cards.schemas.dto import CardCreate, CardMoveInput, CardUpdate
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Card não encontrado", error_code="CARD_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _forbidden(message: str) -> ForbiddenException:
    return ForbiddenException(
        ExceptionData(message=message, error_code="FORBIDDEN"), is_expected=True
    )


class CardService:
    def __init__(self, card_repository: CardRepository, board_repository: BoardRepository) -> None:
        self._card_repo = card_repository
        self._board_repo = board_repository

    def _require_editor(self, team_id: str, user_id: str) -> None:
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._card_repo._db)
        member = team_repo.is_member(team_id, user_id)
        if member is None:
            raise _forbidden("Você não é membro do time deste board")
        if member.role == "viewer":
            raise _forbidden("Usuário com papel viewer não pode editar cards")

    def create(self, payload: CardCreate, owner_id: str) -> Card:
        """Cria card. board_id e team_id vêm do payload; owner_id do JWT.
        columnId é ignorado: card nasce no backlog do time."""
        board = self._board_repo.get_by_id(payload.board_id)
        if board is None:
            raise _not_found()
        self._require_editor(board.team_id, owner_id)

        card = Card(
            board_id=payload.board_id,
            column_id=None,  # Nasce no backlog: columnId do cliente é ignorado
            team_id=payload.team_id,
            title=payload.title,
            description=payload.description,
            type=payload.type,
            priority=payload.priority,
            assignee_id=payload.assignee_id,
            reporter_id=payload.reporter_id or owner_id,
            due_date=payload.due_date,
            start_date=payload.start_date,
            objective=payload.objective,
            points=payload.points,
            fix_version=payload.fix_version,
            budget_project=payload.budget_project,
            parent_id=payload.parent_id,
        )
        try:
            self._card_repo.add(card)
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return card

    def get(self, card_id: str, user_id: str) -> Card:
        card = self._card_repo.get_by_id(card_id)
        if card is None:
            raise _not_found()
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._card_repo._db)
        if team_repo.is_member(card.team_id, user_id) is None:
            raise _forbidden("Você não é membro do time deste card")
        return card

    def list_for_board(
        self,
        board_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Card], int]:
        """Cards de um board (só se o usuário é membro do time)."""
        board = self._board_repo.get_by_id(board_id)
        if board is None:
            raise _not_found()
        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._card_repo._db)
        if team_repo.is_member(board.team_id, user_id) is None:
            raise _forbidden("Você não é membro do time deste board")
        return self._card_repo.list_for_board(board_id, user_id, skip, limit, status_ativo)

    def update(self, card_id: str, payload: CardUpdate, user_id: str) -> Card:
        card = self.get(card_id, user_id)
        self._require_editor(card.team_id, user_id)
        if card.version != payload.expected_version:
            raise _conflict(
                "Versão desatualizada. O card foi modificado por outro usuário.",
                "CARD_VERSION_CONFLICT",
            )
        if payload.title is not None:
            card.title = payload.title
        if payload.description is not None:
            card.description = payload.description
        if payload.type is not None:
            card.type = payload.type
        if payload.priority is not None:
            card.priority = payload.priority
        if payload.assignee_id is not None:
            card.assignee_id = payload.assignee_id
        if payload.due_date is not None:
            card.due_date = payload.due_date
        if payload.start_date is not None:
            card.start_date = payload.start_date
        if payload.objective is not None:
            card.objective = payload.objective
        if payload.points is not None:
            card.points = payload.points
        if payload.fix_version is not None:
            card.fix_version = payload.fix_version
        if payload.budget_project is not None:
            card.budget_project = payload.budget_project
        card.version += 1
        try:
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return card

    def move(self, card_id: str, input_data: CardMoveInput, user_id: str) -> Card:
        """Move card entre colunas (expectedVersion para otimistic locking)."""
        card = self.get(card_id, user_id)
        self._require_editor(card.team_id, user_id)
        if card.version != input_data.expected_version:
            raise _conflict(
                "Versão desatualizada. O card foi modificado por outro usuário.",
                "CARD_VERSION_CONFLICT",
            )
        card.column_id = input_data.column_id
        card.version += 1
        try:
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return card

    def clone(self, card_id: str, user_id: str) -> Card:
        """Clona card (subtarefas, checklist, sem comentários/histórico)."""
        original = self.get(card_id, user_id)
        self._require_editor(original.team_id, user_id)
        from app.modules.kanban_boards.dataproviders.repository import BoardRepository

        board_repo = BoardRepository(self._card_repo._db)
        board = board_repo.get_by_id(original.board_id)
        if board is None:
            raise _not_found()
        cloned = Card(
            board_id=original.board_id,
            column_id=None,
            team_id=original.team_id,
            title=f"Cópia de {original.title}",
            description=original.description,
            type=original.type,
            priority=original.priority,
            assignee_id=original.assignee_id,
            reporter_id=user_id,
            due_date=original.due_date,
            start_date=original.start_date,
            objective=original.objective,
            points=original.points,
            fix_version=original.fix_version,
            budget_project=original.budget_project,
            parent_id=original.parent_id,
        )
        try:
            self._card_repo.add(cloned)
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return cloned
