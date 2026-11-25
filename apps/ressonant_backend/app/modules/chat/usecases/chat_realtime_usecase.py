"""Orquestra persistência, notificações e publicação de eventos de chat.

REST e WebSocket chamam o mesmo método: não existe mais difusão exclusiva do
handler WS, nem mensagem gravada sem evento no barramento.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.common.realtime import (
    RealtimeBus,
    get_realtime_bus,
    new_event,
    room_channel,
    user_channel,
)
from app.modules.chat.dataproviders.repository import (
    ChannelRepository,
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.domain.models import Channel, Conversation, Message
from app.modules.chat.schemas.dto import MessageCreate, MessageInput, MessageResponse
from app.modules.chat.usecases.room_access_usecase import authorize_room
from app.modules.chat.usecases.services import MessageService
from app.modules.notifications.dataproviders.repository import NotificationRepository
from app.modules.notifications.schemas.dto import (
    NotificationCreate,
    NotificationResponse,
)
from app.modules.notifications.usecases.services import NotificationService
from common.errors import ExceptionData, NotFoundException
from sqlalchemy.orm import Session

LOGGER = logging.getLogger(__name__)

TITLES = {
    "mention": "Você foi mencionado",
    "thread_reply": "Nova resposta na thread",
    "system": "Nova mensagem",
}


class ChatRealtimeService:
    def __init__(
        self,
        *,
        db: Session,
        message_service: MessageService,
        message_repository: MessageRepository,
        channels: ChannelRepository,
        conversations: ConversationRepository,
        notifications: NotificationService,
        bus: RealtimeBus,
    ) -> None:
        self._db = db
        self._messages = message_service
        self._message_repo = message_repository
        self._channels = channels
        self._conversations = conversations
        self._notifications = notifications
        self._bus = bus

    def create_message(self, payload: MessageCreate, user_id: str) -> Message:
        """Valida a sala, persiste e publica; autor/workspace vêm do servidor."""
        room = authorize_room(
            self._db, payload.room_kind, payload.room_id, user_id, payload.mention_ids or []
        )
        if payload.parent_id is not None:
            parent = self._message_repo.get_by_id(payload.parent_id)
            if parent is None or parent.room_id != payload.room_id:
                raise NotFoundException(
                    ExceptionData(
                        message="Mensagem-pai não encontrada nesta sala",
                        error_code="MESSAGE_NOT_FOUND",
                    ),
                    is_expected=True,
                )
        message = self._messages.create(
            MessageInput(
                workspace_id=room.workspace_id,
                room_id=payload.room_id,
                room_kind=payload.room_kind,
                author_id=user_id,
                body=payload.body,
                parent_id=payload.parent_id,
                attachments=payload.attachments,
                mention_ids=payload.mention_ids,
            )
        )
        body = MessageResponse.model_validate(message).model_dump(mode="json")
        self._publish(
            room_channel(message.room_kind, message.room_id),
            new_event("message.created", "message", body),
        )
        self._notify(message)
        return message

    def _publish(self, channel: str, event: dict[str, Any]) -> None:
        """Best-effort: falha do barramento nunca vira 500 depois do commit."""
        try:
            self._bus.publish(channel, event)
        except Exception as error:
            LOGGER.warning("realtime_publish_failed error_type=%s", type(error).__name__)

    def _notify(self, message: Message) -> None:
        """Notificação é best-effort: falha não desfaz a mensagem nem o evento."""
        try:
            recipients = self._recipients(message)
            if not recipients:
                return
            excerpt = message.body[:200]
            created = self._notifications.create_many(
                [
                    NotificationCreate(
                        user_id=user_id,
                        kind=kind,
                        title=TITLES[kind],
                        body=excerpt,
                        workspace_id=message.workspace_id,
                        actor_id=message.author_id,
                        message_id=message.id,
                        room_id=message.room_id,
                        room_kind=message.room_kind,
                    )
                    for user_id, kind in recipients
                ]
            )
            for notification in created:
                payload = NotificationResponse.model_validate(notification).model_dump(mode="json")
                self._publish(
                    user_channel(notification.user_id),
                    new_event("notification.created", "notification", payload),
                )
        except Exception as error:
            # Nunca registrar body/title: são conteúdo do usuário (CYB-WS-008).
            LOGGER.warning("chat_notification_failed error_type=%s", type(error).__name__)

    def _recipients(self, message: Message) -> list[tuple[str, str]]:
        room: Channel | Conversation | None
        if message.room_kind == "channel":
            room = self._channels.get_by_id(message.room_id)
        elif message.room_kind == "conversation":
            room = self._conversations.get_by_id(message.room_id)
        else:
            return []
        if room is None or not room.status_ativo:
            return []

        members = self._members(room, message.room_kind)
        members.discard(message.author_id)
        mentions = set(json.loads(message.mention_ids or "[]")) & members
        recipients: dict[str, str] = {user_id: "mention" for user_id in mentions}

        if message.parent_id:
            thread = set(self._message_repo.thread_participants(message.room_id, message.parent_id))
            parent = self._message_repo.get_by_id(message.parent_id)
            if parent is not None:
                thread.add(parent.author_id)
            for user_id in thread & members:
                recipients.setdefault(user_id, "thread_reply")
        elif message.room_kind == "conversation":
            for user_id in members:
                recipients.setdefault(user_id, "system")

        return sorted(recipients.items())

    @staticmethod
    def _members(room: Channel | Conversation, room_kind: str) -> set[str]:
        try:
            raw: Any = json.loads(room.member_ids or "[]")
        except (TypeError, json.JSONDecodeError):
            raw = []
        members = {user_id for user_id in raw if isinstance(user_id, str)}
        created_by = getattr(room, "created_by", None)
        if room_kind == "channel" and created_by:
            members.add(created_by)
        return members


def build_chat_realtime_usecase(db: Session) -> ChatRealtimeService:
    """Fábrica compartilhada pelas rotas REST e pelo handler WebSocket."""
    message_repo = MessageRepository(db)
    return ChatRealtimeService(
        db=db,
        message_service=MessageService(message_repo),
        message_repository=message_repo,
        channels=ChannelRepository(db),
        conversations=ConversationRepository(db),
        notifications=NotificationService(NotificationRepository(db)),
        bus=get_realtime_bus(),
    )
