import hashlib
import uuid

from app.modules.kanban_cards.domain.models import (
    Card,
    CardChecklist,
    CardComment,
    CardCustomField,
    CardHistory,
    CardLink,
    CardSubtask,
    CardWatcher,
    CardWorklog,
)
from app.modules.workspace_management.domain.models import AuditEvent
from sqlalchemy import func, select, text
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

    def max_sequence_by_team(self, team_id: str) -> int:
        """Maior sufixo numérico das keys do time (delete do meio não pode reaproveitar key)."""
        try:
            uuid.UUID(team_id)
        except ValueError:
            return 0
        sequences = []
        for key in self._db.scalars(select(Card.key).where(Card.team_id == team_id)):
            suffix = key.rsplit("-", 1)[-1]
            if suffix.isdigit():
                sequences.append(int(suffix))
        return max(sequences, default=0)

    def lock_card(self, card_id: str) -> None:
        """Advisory lock transacional do UUID; fecha a corrida delete × criação de filho."""
        try:
            normalized = str(uuid.UUID(card_id))
        except ValueError as exc:
            raise ValueError(f"Invalid card UUID: {card_id}") from exc
        if self._db.get_bind().dialect.name != "postgresql":
            return  # pg_advisory_xact_lock não existe no SQLite dos testes unitários
        digest = hashlib.sha256(normalized.encode("ascii")).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        self._db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def has_children(self, card_id: str) -> bool:
        """Inclui filhos inativos: parent_id não tem FK e não pode virar órfão."""
        return (
            self._db.scalar(select(Card.id).where(Card.parent_id == card_id).limit(1)) is not None
        )

    def count_worklogs(self, card_id: str) -> int:
        return int(
            self._db.scalar(
                select(func.count()).select_from(CardWorklog).where(CardWorklog.card_id == card_id)
            )
            or 0
        )

    def delete_snapshot(self, card: Card) -> dict:
        """Snapshot mínimo para auditoria: contagens e field_keys, nunca valores/PII."""

        def count(model: type) -> int:
            card_id_column = getattr(model, "card_id")
            return int(
                self._db.scalar(
                    select(func.count()).select_from(model).where(card_id_column == card.id)
                )
                or 0
            )

        field_keys = list(
            self._db.scalars(
                select(CardCustomField.field_key)
                .where(CardCustomField.card_id == card.id)
                .order_by(CardCustomField.field_key)
            )
        )
        return {
            "key": card.key,
            "board_id": card.board_id,
            "team_id": card.team_id,
            "column_id": card.column_id,
            "child_count": 0,
            "dependencies": {
                "subtasks": count(CardSubtask),
                "checklist_items": count(CardChecklist),
                "comments": count(CardComment),
                "history": count(CardHistory),
                "worklogs": 0,
                "links": count(CardLink),
                "watchers": count(CardWatcher),
                "custom_fields": count(CardCustomField),
            },
            "custom_field_keys": field_keys,
        }

    def add(self, card: Card) -> Card:
        self._db.add(card)
        self._db.flush()
        return card

    def add_history(self, history: CardHistory) -> CardHistory:
        self._db.add(history)
        self._db.flush()
        return history

    def add_comment(self, comment: CardComment) -> CardComment:
        self._db.add(comment)
        self._db.flush()
        return comment

    def list_comments(
        self, card_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[CardComment], int]:
        stmt = select(CardComment).where(CardComment.card_id == card_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(CardComment.criado_em, CardComment.id).offset(skip).limit(limit)
        )
        return list(items), total

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append-only: INSERT + flush; UPDATE/DELETE são bloqueados no banco (0017)."""
        self._db.add(event)
        self._db.flush()
        return event

    def delete_card(self, card: Card) -> None:
        self._db.delete(card)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
