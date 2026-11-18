import uuid

from app.modules.reactions.dataproviders.repository import ReactionRepository
from app.modules.reactions.domain.models import MessageReaction
from app.modules.reactions.schemas.dto import ReactionList, ReactionResponse, ReactionToggle


class ReactionService:
    def __init__(self, repository: ReactionRepository) -> None:
        self._repo = repository

    def list_by_message_ids(self, message_ids: list[str]) -> ReactionList:
        reactions = self._repo.list_by_message_ids(message_ids)
        return ReactionList(
            items=[ReactionResponse.model_validate(r) for r in reactions],
            total=len(reactions),
        )

    def toggle(self, payload: ReactionToggle) -> dict:
        try:
            uuid.UUID(payload.message_id)
            uuid.UUID(payload.user_id)
        except ValueError:
            return {"active": False}
        existing = self._repo.get_by_message_user_emoji(
            payload.message_id, payload.user_id, payload.emoji
        )
        if existing:
            self._repo.delete(existing)
            self._repo.commit()
            return {"active": False}
        reaction = MessageReaction(
            message_id=payload.message_id,
            user_id=payload.user_id,
            emoji=payload.emoji,
        )
        try:
            self._repo.add(reaction)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return {"active": True}
