"""Criação autenticada de notificação: destinatário e ator vêm do token."""

from __future__ import annotations

import json
from typing import Any

from app.modules.chat.dataproviders.repository import (
    ChannelRepository,
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.domain.models import Channel, Conversation
from app.modules.notifications.dataproviders.repository import NotificationRepository
from app.modules.notifications.domain.models import AppNotification
from app.modules.notifications.schemas.dto import NotificationCreate, NotificationPublicCreate
from app.modules.notifications.usecases.services import NotificationService
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from common.errors import (
    BadRequestException,
    ExceptionData,
    ForbiddenException,
    NotFoundException,
)
from sqlalchemy.orm import Session


def _error(message: str, code: str) -> ExceptionData:
    return ExceptionData(message=message, error_code=code)


def _get_room(db: Session, room_kind: str | None, room_id: str) -> Channel | Conversation | None:
    if room_kind == "channel":
        return ChannelRepository(db).get_by_id(room_id)
    if room_kind == "conversation":
        return ConversationRepository(db).get_by_id(room_id)
    return None


def _is_room_member(room: Channel | Conversation, room_kind: str, user_id: str) -> bool:
    try:
        raw: Any = json.loads(room.member_ids or "[]")
    except (TypeError, json.JSONDecodeError):
        return False
    members = {item for item in raw if isinstance(item, str)}
    if room_kind == "channel" and getattr(room, "created_by", None):
        members.add(room.created_by)
    return user_id in members


def create_notification_for_user(
    db: Session, payload: NotificationPublicCreate, user_id: str
) -> AppNotification:
    """Valida workspace/ator/sala antes de gravar na caixa do usuário autenticado."""
    workspace = WorkspaceRepository(db).get_by_id(payload.workspace_id)
    if workspace is None or not workspace.status_ativo:
        raise NotFoundException(
            _error("Workspace não encontrado", "WORKSPACE_NOT_FOUND"), is_expected=True
        )
    if WorkspaceRepository(db).is_member(workspace.id, user_id) is None:
        raise ForbiddenException(
            _error("Você não é membro deste workspace", "FORBIDDEN"), is_expected=True
        )
    if payload.actor_id is not None and payload.actor_id != user_id:
        raise ForbiddenException(
            _error("actor_id deve ser o usuário autenticado", "FORBIDDEN"), is_expected=True
        )

    if payload.room_id is not None:
        if payload.room_kind not in {"channel", "conversation"}:
            raise BadRequestException(
                _error("room_kind é obrigatório com room_id", "INVALID_ROOM_KIND"),
                is_expected=True,
            )
        room = _get_room(db, payload.room_kind, payload.room_id)
        if room is None or not room.status_ativo or room.workspace_id != workspace.id:
            raise NotFoundException(
                _error("Sala não encontrada neste workspace", "ROOM_NOT_FOUND"),
                is_expected=True,
            )
        if not _is_room_member(room, payload.room_kind, user_id):
            raise ForbiddenException(
                _error("Você não é membro desta sala", "FORBIDDEN"), is_expected=True
            )

    if payload.message_id is not None:
        message = MessageRepository(db).get_by_id(payload.message_id)
        if message is None or message.workspace_id != workspace.id:
            raise NotFoundException(
                _error("Mensagem não encontrada neste workspace", "MESSAGE_NOT_FOUND"),
                is_expected=True,
            )
        if payload.room_id is not None and message.room_id != payload.room_id:
            raise BadRequestException(
                _error("Mensagem não pertence à sala informada", "INVALID_MESSAGE_ROOM"),
                is_expected=True,
            )

    return NotificationService(NotificationRepository(db)).create(
        NotificationCreate(
            user_id=user_id,
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            workspace_id=workspace.id,
            actor_id=user_id,
            message_id=payload.message_id,
            room_id=payload.room_id,
            room_kind=payload.room_kind,
        )
    )
