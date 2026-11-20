"""WebSocket de chat com persistência e difusão por sala no processo."""

import asyncio
import json
from typing import Annotated, Any

from app.database.engine import get_db
from app.modules.auth.usecases.tokens import decode_access_token
from app.modules.chat.dataproviders.repository import (
    ChannelRepository,
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.domain.models import Channel, Conversation
from app.modules.chat.schemas.dto import MessageCreate, MessageResponse
from app.modules.chat.usecases.services import MessageService
from app.modules.user.dataproviders.repository import UserRepository
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

router = APIRouter(tags=["chat websocket"])


class SocketMessage(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: str | None = None
    attachments: list[dict[str, Any]] | None = None
    mention_ids: list[str] | None = None


class RoomConnectionManager:
    """Mantém as conexões WebSocket agrupadas por tipo e identificador de sala."""

    def __init__(self) -> None:
        self._rooms: dict[tuple[str, str], set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        room: tuple[str, str],
        websocket: WebSocket,
        subprotocol: str | None = None,
    ) -> None:
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            self._rooms.setdefault(room, set()).add(websocket)

    async def disconnect(self, room: tuple[str, str], websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._rooms.get(room)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._rooms.pop(room, None)

    async def broadcast(self, room: tuple[str, str], event: dict[str, Any]) -> None:
        async with self._lock:
            connections = tuple(self._rooms.get(room, ()))
        stale: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(connection)
        for connection in stale:
            await self.disconnect(room, connection)


manager = RoomConnectionManager()


def _authenticate(db: Session, token: str | None):
    user_id = decode_access_token(token or "")
    if user_id is None:
        return None
    user = UserRepository(db).get_by_id(user_id)
    return user if user is not None and user.status_ativo else None


def _get_room(db: Session, room_kind: str, room_id: str) -> Channel | Conversation | None:
    if room_kind == "channel":
        return ChannelRepository(db).get_by_id(room_id)
    if room_kind == "conversation":
        return ConversationRepository(db).get_by_id(room_id)
    return None


def _is_member(room: Channel | Conversation, room_kind: str, user_id: str) -> bool:
    try:
        member_ids = json.loads(room.member_ids or "[]")
    except (TypeError, json.JSONDecodeError):
        member_ids = []
    if room_kind == "channel":
        return user_id == room.created_by or user_id in member_ids
    return user_id in member_ids


def _persist_message(
    db: Session,
    *,
    workspace_id: str,
    room_id: str,
    room_kind: str,
    author_id: str,
    payload: SocketMessage,
) -> dict[str, Any]:
    service = MessageService(MessageRepository(db))
    message = service.create(
        MessageCreate(
            workspace_id=workspace_id,
            room_id=room_id,
            room_kind=room_kind,
            author_id=author_id,
            body=payload.body,
            parent_id=payload.parent_id,
            attachments=payload.attachments,
            mention_ids=payload.mention_ids,
        )
    )
    return MessageResponse.model_validate(message).model_dump(mode="json")


@router.websocket("/ws/{room_kind}/{room_id}")
async def chat_room(
    websocket: WebSocket,
    room_kind: str,
    room_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Connecta em `/ws/channel/{id}` ou `/ws/conversation/{id}` com subprotocolos bearer."""
    if room_kind not in {"channel", "conversation"}:
        await websocket.close(code=4404)
        return

    protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if value.strip()
    ]
    if len(protocols) != 2 or protocols[0].lower() != "bearer":
        await websocket.close(code=4401)
        return
    token = protocols[1]
    user, room = await run_in_threadpool(
        lambda: (_authenticate(db, token), _get_room(db, room_kind, room_id))
    )
    if user is None:
        await websocket.close(code=4401)
        return
    if room is None or not room.status_ativo:
        await websocket.close(code=4404)
        return
    if not _is_member(room, room_kind, user.id):
        await websocket.close(code=4403)
        return

    room_key = (room_kind, room_id)
    await manager.connect(room_key, websocket, subprotocol="bearer")
    try:
        while True:
            try:
                raw_payload = await websocket.receive_json()
                payload = SocketMessage.model_validate(raw_payload)
            except ValidationError:
                await websocket.send_json(
                    {"type": "error", "message": "Formato de mensagem inválido"}
                )
                continue
            except (ValueError, TypeError):
                await websocket.send_json(
                    {"type": "error", "message": "Formato de mensagem inválido"}
                )
                continue

            try:
                message = await run_in_threadpool(
                    _persist_message,
                    db,
                    workspace_id=room.workspace_id,
                    room_id=room_id,
                    room_kind=room_kind,
                    author_id=user.id,
                    payload=payload,
                )
            except Exception:
                await websocket.send_json(
                    {"type": "error", "message": "Não foi possível persistir a mensagem"}
                )
                continue
            await manager.broadcast(
                room_key,
                {"type": "message", "message": message},
            )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(room_key, websocket)
