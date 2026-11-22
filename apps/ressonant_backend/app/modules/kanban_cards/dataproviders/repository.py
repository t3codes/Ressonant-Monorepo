import uuid

from app.modules.kanban_cards.domain.models import Card, CardHistory
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class CardRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, card_id: str) -> Card | None:
        try:
            uuid.UUID(card_id)
        except ValueError:
            return None
        return self._db.get(Card, card_id)

    def list_for_board(
        self,
        board_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Card], int]:
        """Cards de um board onde o usuário é membro do time."""
        try:
            uuid.UUID(board_id)
            uuid.UUID(user_id)
        except ValueError:
            return [], 0
        stmt = select(Card).where(Card.board_id == board_id)
        if status_ativo is not None:
            stmt = stmt.where(Card.status_ativo == status_ativo)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(stmt.order_by(Card.criado_em, Card.id).offset(skip).limit(limit))
        return list(items), total

    def count_by_team(self, team_id: str) -> int:
        try:
            uuid.UUID(team_id)
        except ValueError:
            return 0
        return (
            self._db.scalar(select(func.count()).select_from(Card).where(Card.team_id == team_id))
            or 0
        )

    def add(self, card: Card) -> Card:
        self._db.add(card)
        self._db.flush()
        return card

    def add_history(self, history: CardHistory) -> CardHistory:
        self._db.add(history)
        self._db.flush()
        return history

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
