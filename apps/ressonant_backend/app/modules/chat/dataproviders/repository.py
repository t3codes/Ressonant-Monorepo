import uuid

from app.modules.chat.domain.models import Channel, Conversation, Message
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class ChannelRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, channel_id: str) -> Channel | None:
        try:
            uuid.UUID(channel_id)
        except ValueError:
            return None
        return self._db.get(Channel, channel_id)

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Channel], int]:
        stmt = select(Channel).where(Channel.workspace_id == workspace_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(Channel.criado_em, Channel.id).offset(skip).limit(limit)
        )
        return list(items), total

    def get_default_for_workspace(self, workspace_id: str) -> Channel | None:
        """Canal geral/default do workspace para onboarding por convite."""
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return None
        channels = list(
            self._db.scalars(
                select(Channel)
                .where(Channel.workspace_id == workspace_id, Channel.status_ativo.is_(True))
                .order_by(Channel.criado_em, Channel.id)
            )
        )
        for channel in channels:
            slug = (channel.slug or "").lower()
            name = (channel.name or "").strip().lower()
            if slug == "geral" or slug.startswith("geral-") or name == "geral":
                return channel
        return channels[0] if channels else None

    def add(self, channel: Channel) -> Channel:
        self._db.add(channel)
        self._db.flush()
        return channel

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, conversation_id: str) -> Conversation | None:
        try:
            uuid.UUID(conversation_id)
        except ValueError:
            return None
        return self._db.get(Conversation, conversation_id)

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Conversation], int]:
        stmt = select(Conversation).where(Conversation.workspace_id == workspace_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(Conversation.criado_em, Conversation.id).offset(skip).limit(limit)
        )
        return list(items), total

    def add(self, conversation: Conversation) -> Conversation:
        self._db.add(conversation)
        self._db.flush()
        return conversation

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, message_id: str) -> Message | None:
        try:
            uuid.UUID(message_id)
        except ValueError:
            return None
        return self._db.get(Message, message_id)

    def list_by_room(
        self, room_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Message], int]:
        stmt = select(Message).where(Message.room_id == room_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(Message.criado_em, Message.id).offset(skip).limit(limit)
        )
        return list(items), total

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Message], int]:
        stmt = select(Message).where(Message.workspace_id == workspace_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(Message.criado_em, Message.id).offset(skip).limit(limit)
        )
        return list(items), total

    def add(self, message: Message) -> Message:
        self._db.add(message)
        self._db.flush()
        return message

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
