"""Autorização de sala compartilhada por REST e WebSocket.

Autor/workspace jamais são aceitos do cliente: a sala é a fonte da verdade.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.modules.chat.dataproviders.repository import ChannelRepository, ConversationRepository
from app.modules.chat.domain.models import Channel, Conversation
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from common.errors import ExceptionData, ForbiddenException, NotFoundException
from sqlalchemy.orm import Session


def _not_found(entity: str) -> NotFoundException:
    return NotFoundException(
        ExceptionData(message=f"{entity} não encontrado", error_code=f"{entity.upper()}_NOT_FOUND"),
        is_expected=True,
    )


def _forbidden(message: str) -> ForbiddenException:
    return ForbiddenException(
        ExceptionData(message=message, error_code="FORBIDDEN"), is_expected=True
    )


def _get_room(db: Session, room_kind: str, room_id: str) -> Channel | Conversation | None:
    if room_kind == "channel":
        return ChannelRepository(db).get_by_id(room_id)
    if room_kind == "conversation":
        return ConversationRepository(db).get_by_id(room_id)
    return None


def _room_member_ids(room: Channel | Conversation) -> set[str]:
    try:
        raw: Any = json.loads(room.member_ids or "[]")
    except (TypeError, json.JSONDecodeError):
        return set()
    members = {user_id for user_id in raw if isinstance(user_id, str)}
    created_by = getattr(room, "created_by", None)
    if created_by:
        members.add(created_by)
    return members


def _is_room_member(room: Channel | Conversation, room_kind: str, user_id: str) -> bool:
    """Canal inclui o criador mesmo quando ele não está no JSON de membros."""
    if room_kind == "conversation":
        try:
            raw: Any = json.loads(room.member_ids or "[]")
        except (TypeError, json.JSONDecodeError):
            return False
        return user_id in {item for item in raw if isinstance(item, str)}
    return user_id in _room_member_ids(room)


def authorize_room(
    db: Session,
    room_kind: str,
    room_id: str,
    user_id: str,
    mention_ids: Iterable[str] = (),
) -> Channel | Conversation:
    """Exige sala ativa, workspace ativo, membro das duas estruturas e menções válidas."""
    room = _get_room(db, room_kind, room_id)
    if room is None or not room.status_ativo:
        raise _not_found("Room")
    workspace = WorkspaceRepository(db).get_by_id(room.workspace_id)
    if workspace is None or not workspace.status_ativo:
        raise _not_found("Workspace")
    if WorkspaceRepository(db).is_member(room.workspace_id, user_id) is None:
        raise _forbidden("Você não é membro deste workspace")
    members = _room_member_ids(room)
    if not _is_room_member(room, room_kind, user_id):
        raise _forbidden("Você não é membro desta sala")
    if not set(mention_ids) <= members:
        raise _forbidden("Menção permitida somente a membros da sala")
    return room
