import json
import re

from app.common.exceptions import ConflictException
from app.modules.chat.dataproviders.repository import (
    ChannelRepository,
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.domain.models import Channel, Conversation, Message
from app.modules.chat.schemas.dto import (
    ChannelCreate,
    ConversationCreate,
    MessageInput,
    MessageUpdate,
)
from common.errors import ExceptionData, ForbiddenException, NotFoundException


def _not_found(entity: str) -> NotFoundException:
    return NotFoundException(
        ExceptionData(message=f"{entity} não encontrado", error_code=f"{entity.upper()}_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _forbidden(message: str) -> ForbiddenException:
    return ForbiddenException(
        ExceptionData(message=message, error_code="FORBIDDEN"), is_expected=True
    )


class ChannelService:
    def __init__(self, repository: ChannelRepository) -> None:
        self._repo = repository

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Channel], int]:
        return self._repo.list_by_workspace(workspace_id, skip, limit)

    def get_by_id(self, channel_id: str) -> Channel | None:
        return self._repo.get_by_id(channel_id)

    def add_channel(
        self, payload: ChannelCreate, created_by: str, *, slug: str | None = None
    ) -> Channel:
        """Prepara o canal na Session; a transação fica com quem chama."""
        channel_slug = slug
        if channel_slug is None:
            channel_slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
        channel = Channel(
            workspace_id=payload.workspace_id,
            name=payload.name,
            slug=channel_slug,
            topic=payload.topic,
            visibility=payload.visibility,
            member_ids=json.dumps([created_by]),
            created_by=created_by,
        )
        self._repo.add(channel)
        return channel

    def create(self, payload: ChannelCreate, created_by: str) -> Channel:
        try:
            channel = self.add_channel(payload, created_by)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return channel

    def add_member(self, channel_id: str, user_id: str) -> Channel:
        channel = self.get_by_id(channel_id)
        if channel is None:
            raise _not_found("Channel")
        members = json.loads(channel.member_ids or "[]")
        if user_id not in members:
            members.append(user_id)
            channel.member_ids = json.dumps(members)
            try:
                self._repo.commit()
            except Exception:
                self._repo.rollback()
                raise
        return channel


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repo = repository

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Conversation], int]:
        return self._repo.list_by_workspace(workspace_id, skip, limit)

    def get_by_id(self, conversation_id: str) -> Conversation | None:
        return self._repo.get_by_id(conversation_id)

    def create(self, payload: ConversationCreate) -> Conversation:
        conversation = Conversation(
            workspace_id=payload.workspace_id,
            member_ids=json.dumps(payload.member_ids),
        )
        try:
            self._repo.add(conversation)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return conversation


class MessageService:
    def __init__(self, repository: MessageRepository) -> None:
        self._repo = repository

    def list_by_room(
        self, room_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Message], int]:
        return self._repo.list_by_room(room_id, skip, limit)

    def list_by_workspace(
        self, workspace_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Message], int]:
        return self._repo.list_by_workspace(workspace_id, skip, limit)

    def get_by_id(self, message_id: str) -> Message | None:
        return self._repo.get_by_id(message_id)

    def create(self, payload: MessageInput) -> Message:
        message = Message(
            workspace_id=payload.workspace_id,
            room_id=payload.room_id,
            room_kind=payload.room_kind,
            author_id=payload.author_id,
            body=payload.body,
            parent_id=payload.parent_id,
            attachments=json.dumps(payload.attachments or []),
            mention_ids=json.dumps(payload.mention_ids or []),
        )
        try:
            self._repo.add(message)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return message

    def update(self, message_id: str, payload: MessageUpdate, user_id: str) -> Message:
        message = self.get_by_id(message_id)
        if message is None:
            raise _not_found("Message")
        if message.author_id != user_id:
            raise _forbidden("Somente o autor pode editar a mensagem")
        message.body = payload.body
        if payload.mention_ids is not None:
            message.mentionIds = json.dumps(payload.mention_ids)
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return message

    def soft_delete(self, message_id: str, user_id: str) -> None:
        message = self.get_by_id(message_id)
        if message is None:
            raise _not_found("Message")
        if message.author_id != user_id:
            raise _forbidden("Somente o autor pode excluir a mensagem")
        message.status_ativo = False
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
