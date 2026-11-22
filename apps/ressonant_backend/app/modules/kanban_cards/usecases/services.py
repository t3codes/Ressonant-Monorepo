from datetime import UTC, datetime

from app.common.exceptions import ConflictException
from app.modules.kanban_boards.dataproviders.repository import BoardRepository
from app.modules.kanban_cards.dataproviders.repository import CardRepository
from app.modules.kanban_cards.domain.models import Card, CardHistory
from app.modules.kanban_cards.schemas.dto import (
    CardBlockInput,
    CardCreate,
    CardMoveInput,
    CardUnblockInput,
    CardUpdate,
)
from common.errors import ExceptionData, ForbiddenException, NotFoundException
from sqlalchemy.exc import IntegrityError


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
        """Cria card no time do board; owner_id vem do JWT.

        columnId é ignorado: card nasce no backlog do time.
        """
        board = self._board_repo.get_by_id(payload.board_id)
        if board is None:
            raise _not_found()
        if payload.team_id != board.team_id:
            raise _conflict("team_id do card diverge do time do board", "CARD_TEAM_MISMATCH")
        self._require_editor(board.team_id, owner_id)

        from app.modules.teams.dataproviders.repository import TeamRepository

        team_repo = TeamRepository(self._card_repo._db)
        team = team_repo.get_by_id(board.team_id)
        if team is None:
            raise NotFoundException(
                ExceptionData(message="Team não encontrado", error_code="TEAM_NOT_FOUND"),
                is_expected=True,
            )
        if not team.key_prefix:
            raise _conflict("Time sem prefixo de chave configurado", "TEAM_KEY_PREFIX_MISSING")

        # count + insert não é atômico; o índice único é a última linha de defesa.
        sequence = self._card_repo.count_by_team(board.team_id) + 1
        key = f"{team.key_prefix}-{sequence}"[:50]

        card = Card(
            key=key,
            board_id=payload.board_id,
            column_id=None,  # Nasce no backlog: columnId do cliente é ignorado
            team_id=board.team_id,
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
        except IntegrityError as exc:
            self._card_repo.rollback()
            raise _conflict("Chave de card já existe neste time", "CARD_KEY_CONFLICT") from exc
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

    def _can_retrocede(self, card: Card, actor_id: str, actor_is_interno_adm: bool) -> bool:
        if actor_is_interno_adm:
            return True
        board = self._board_repo.get_by_id(card.board_id)
        if board is None:
            return False
        from app.modules.teams.dataproviders.repository import TeamRepository
        from app.modules.workspace.dataproviders.repository import WorkspaceRepository

        ws_repo = WorkspaceRepository(self._card_repo._db)
        team_repo = TeamRepository(self._card_repo._db)
        ws = ws_repo.get_by_id(board.workspace_id)
        if ws and ws.owner_id == actor_id:
            return True
        ws_member = ws_repo.is_member(board.workspace_id, actor_id)
        if ws_member and ws_member.role == "admin":
            return True  # gestor/admin workspace
        team = team_repo.get_by_id(card.team_id)
        member = team_repo.is_member(card.team_id, actor_id)
        if team and team.owner_id == actor_id:
            return True
        if member and member.role == "admin":
            return True
        if member and member.can_retrocede and card.assignee_id == actor_id:
            return True
        return False

    def move(
        self,
        card_id: str,
        input_data: CardMoveInput,
        user_id: str,
        actor_is_interno_adm: bool = False,
    ) -> Card:
        """Move card entre colunas (expectedVersion para optimistic locking)."""
        card = self.get(card_id, user_id)
        self._require_editor(card.team_id, user_id)
        if card.is_blocked:
            raise _conflict("Card bloqueado não pode ser movido", "CARD_BLOCKED")
        if card.version != input_data.expected_version:
            raise _conflict(
                "Versão desatualizada. O card foi modificado por outro usuário.",
                "CARD_VERSION_CONFLICT",
            )
        from app.modules.kanban_boards.dataproviders.repository import BoardColumnRepository

        col_repo = BoardColumnRepository(self._card_repo._db)
        origin_col = col_repo.get_by_id(card.column_id) if card.column_id else None
        dest_col = col_repo.get_by_id(input_data.column_id)
        if dest_col is None or dest_col.board_id != card.board_id:
            raise _conflict("Coluna de destino inválida", "BOARD_COLUMN_INVALID")
        origin_pos = origin_col.position if origin_col else -1
        dest_pos = dest_col.position
        is_backward = dest_pos < origin_pos
        if is_backward and not self._can_retrocede(card, user_id, actor_is_interno_adm):
            raise _forbidden("Você não tem permissão para retroceder este card")

        old_column = card.column_id
        card.column_id = input_data.column_id
        card.version += 1
        self._card_repo.add_history(
            CardHistory(
                card_id=card.id,
                event_type="moved_backward" if is_backward else "moved",
                field_name="column_id",
                old_value=str(old_column) if old_column else None,
                new_value=str(input_data.column_id),
                author_id=user_id,
            )
        )
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

    def _is_privileged_unblocker(
        self, card: Card, actor_id: str, actor_is_interno_adm: bool
    ) -> bool:
        if actor_is_interno_adm:
            return True
        board = self._board_repo.get_by_id(card.board_id)
        if board is None:
            return False
        from app.modules.workspace.dataproviders.repository import WorkspaceRepository

        ws_repo = WorkspaceRepository(self._card_repo._db)
        ws = ws_repo.get_by_id(board.workspace_id)
        return ws is not None and ws.owner_id == actor_id

    def block(
        self,
        card_id: str,
        payload: CardBlockInput,
        user_id: str,
        actor_is_interno_adm: bool = False,
    ) -> Card:
        card = self.get(card_id, user_id)
        self._require_editor(card.team_id, user_id)
        if card.version != payload.expected_version:
            raise _conflict(
                "Versão desatualizada. O card foi modificado por outro usuário.",
                "CARD_VERSION_CONFLICT",
            )
        if card.is_blocked:
            raise _conflict("Card já está bloqueado", "CARD_ALREADY_BLOCKED")
        reason = payload.reason.strip()
        if len(reason) < 3:
            raise _conflict("Justificativa do bloqueio é obrigatória", "CARD_BLOCK_REASON_REQUIRED")
        card.is_blocked = True
        card.block_reason = reason
        card.blocked_by = user_id
        card.blocked_at = datetime.now(UTC)
        card.version += 1
        self._card_repo.add_history(
            CardHistory(
                card_id=card.id,
                event_type="blocked",
                field_name="is_blocked",
                old_value="false",
                new_value=reason,
                author_id=user_id,
            )
        )
        try:
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return card

    def unblock(
        self,
        card_id: str,
        payload: CardUnblockInput,
        user_id: str,
        actor_is_interno_adm: bool = False,
    ) -> Card:
        card = self.get(card_id, user_id)
        self._require_editor(card.team_id, user_id)
        if card.version != payload.expected_version:
            raise _conflict(
                "Versão desatualizada. O card foi modificado por outro usuário.",
                "CARD_VERSION_CONFLICT",
            )
        if not card.is_blocked:
            raise _conflict("Card não está bloqueado", "CARD_NOT_BLOCKED")
        is_blocker = card.blocked_by == user_id
        is_privileged = self._is_privileged_unblocker(card, user_id, actor_is_interno_adm)
        justification = (payload.justification or "").strip() if payload.justification else ""
        if not is_blocker and not is_privileged:
            raise _forbidden("Somente quem bloqueou o card ou owner/interno_adm pode desbloquear")
        if is_privileged and not is_blocker and len(justification) < 3:
            raise _conflict(
                "Justificativa obrigatória para desbloqueio por owner/interno_adm",
                "CARD_UNBLOCK_JUSTIFICATION_REQUIRED",
            )
        old_reason = card.block_reason
        card.is_blocked = False
        card.block_reason = None
        card.blocked_by = None
        card.blocked_at = None
        card.version += 1
        self._card_repo.add_history(
            CardHistory(
                card_id=card.id,
                event_type="unblocked",
                field_name="is_blocked",
                old_value=old_reason,
                new_value=justification or f"unblocked_by:{user_id}",
                author_id=user_id,
            )
        )
        try:
            self._card_repo.commit()
        except Exception:
            self._card_repo.rollback()
            raise
        return card
