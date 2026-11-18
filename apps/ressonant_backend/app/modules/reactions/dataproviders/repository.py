import uuid

from app.modules.reactions.domain.models import MessageReaction
from sqlalchemy import select
from sqlalchemy.orm import Session


class ReactionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_message_ids(self, message_ids: list[str]) -> list[MessageReaction]:
        if not message_ids:
            return []
        return self._db.scalars(
            select(MessageReaction).where(MessageReaction.message_id.in_(message_ids))
        ).all()

    def get_by_message_user_emoji(
        self, message_id: str, user_id: str, emoji: str
    ) -> MessageReaction | None:
        try:
            uuid.UUID(message_id)
            uuid.UUID(user_id)
        except ValueError:
            return None
        return self._db.scalar(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
        )

    def add(self, reaction: MessageReaction) -> MessageReaction:
        self._db.add(reaction)
        self._db.flush()
        return reaction

    def delete(self, reaction: MessageReaction) -> None:
        self._db.delete(reaction)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
