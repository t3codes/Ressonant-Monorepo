"""WebSocket de chat: sala por conexão, eventos via barramento (local ou Redis)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import jwt
from app.common.realtime import get_realtime_bus, room_channel, user_channel, validate_envelope
from app.config.settings import get_settings
from app.database.engine import get_db, get_session_factory
from app.modules.auth.usecases.tokens import decode_access_claims
from app.modules.chat.schemas.dto import MessageCreate
from app.modules.chat.usecases.chat_realtime_usecase import build_chat_realtime_usecase
from app.modules.chat.usecases.room_access_usecase import authorize_room
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from common.errors import ApplicationException, ForbiddenException, NotFoundException
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["chat websocket"])

WS_MAX_FRAME_BYTES = 16_384
WS_MAX_QUEUE = 256
WS_RATE_MAX_MESSAGES = 10
WS_RATE_WINDOW_SECONDS = 5
AUTH_CACHE_TTL_SECONDS = 3
MAX_ATTACHMENTS = 10
MAX_MENTIONS = 50


class SocketMessage(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: str | None = None
    attachments: list[dict[str, Any]] | None = Field(default=None, max_length=MAX_ATTACHMENTS)
    mention_ids: list[str] | None = Field(default=None, max_length=MAX_MENTIONS)


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    user_id: str
    workspace_id: str
    room_kind: str
    room_id: str
    expires_at: datetime
    subprotocol: str
    release_room: Callable[[], None]
    release_user: Callable[[], None]
    released: bool = field(default=False, init=False)


class RoomConnectionManager:
    """Conexões locais indexadas por workspace + sala e workspace + usuário."""

    def __init__(self) -> None:
        self._rooms: dict[tuple[str, str, str], set[Connection]] = {}
        self._users: dict[tuple[str, str], set[Connection]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_key: tuple[str, str, str], connection: Connection) -> None:
        await connection.websocket.accept(subprotocol=connection.subprotocol)
        async with self._lock:
            self._rooms.setdefault(room_key, set()).add(connection)
            self._users.setdefault((connection.workspace_id, connection.user_id), set()).add(
                connection
            )

    async def disconnect(self, room_key: tuple[str, str, str], connection: Connection) -> None:
        async with self._lock:
            connections = self._rooms.get(room_key)
            if connections is not None:
                connections.discard(connection)
                if not connections:
                    self._rooms.pop(room_key, None)
            user_connections = self._users.get((connection.workspace_id, connection.user_id))
            if user_connections is not None:
                user_connections.discard(connection)
                if not user_connections:
                    self._users.pop((connection.workspace_id, connection.user_id), None)

    async def broadcast(self, room_key: tuple[str, str, str], event: dict[str, Any]) -> None:
        async with self._lock:
            connections = tuple(self._rooms.get(room_key, ()))
        await self._send(connections, room_key, event)

    async def broadcast_user(self, user_key: tuple[str, str], event: dict[str, Any]) -> None:
        async with self._lock:
            connections = tuple(self._users.get(user_key, ()))
        await self._send(connections, None, event)

    async def _send(
        self,
        connections: tuple[Connection, ...],
        room_key: tuple[str, str, str] | None,
        event: dict[str, Any],
    ) -> None:
        for connection in connections:
            if not await _revalidate(connection):
                await self.drop(connection, room_key)
                continue
            try:
                await connection.websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect, OSError):
                await self.drop(connection, room_key, close=False)

    async def drop(
        self,
        connection: Connection,
        room_key: tuple[str, str, str] | None,
        *,
        close: bool = True,
        code: int = 4403,
    ) -> None:
        """Revogação na entrega: fecha 4403 e libera as inscrições do canal."""
        if close:
            try:
                await connection.websocket.close(code=code)
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass
        if room_key is None:
            room_key = (connection.workspace_id, connection.room_kind, connection.room_id)
        await self.disconnect(room_key, connection)
        if connection.released:
            return
        connection.released = True
        connection.release_room()
        connection.release_user()


manager = RoomConnectionManager()

# Em testes unitários o banco é um SQLite em memória injetado por dependency override;
# a revalidação precisa abrir sessões no mesmo banco.
_revalidation_factory: Callable[[], Session] | None = None


def _open_revalidation_session() -> Session:
    factory = _revalidation_factory or get_session_factory()
    return factory()


_loop: asyncio.AbstractEventLoop | None = None
_queue: asyncio.Queue[tuple[str, dict[str, Any]]] | None = None
_task: asyncio.Task | None = None
_channel_refs: dict[str, list[Any]] = {}


@lru_cache(maxsize=4096)
def _cached_access(
    bucket: int, workspace_id: str, room_kind: str, room_id: str, user_id: str
) -> bool:
    """Cache curto por janela de tempo: não é uma consulta por frame."""
    with _open_revalidation_session() as db:
        user = UserRepository(db).get_by_id(user_id)
        if user is None or not user.status_ativo:
            return False
        workspace = WorkspaceRepository(db).get_by_id(workspace_id)
        if workspace is None or not workspace.status_ativo:
            return False
        try:
            room = authorize_room(db, room_kind, room_id, user_id)
        except ApplicationException:
            return False
        return room.workspace_id == workspace_id


async def _revalidate(connection: Connection) -> bool:
    if datetime.now(UTC) >= connection.expires_at:
        return False
    bucket = int(time.monotonic() // AUTH_CACHE_TTL_SECONDS)
    return await run_in_threadpool(
        _cached_access,
        bucket,
        connection.workspace_id,
        connection.room_kind,
        connection.room_id,
        connection.user_id,
    )


def _subscribe_channel(channel: str) -> Callable[[], None]:
    """Registra um listener por canal com contagem de conexões (sem entrega duplicada)."""

    def enqueue(item: tuple[str, dict[str, Any]]) -> None:
        if _queue is None:
            return
        try:
            _queue.put_nowait(item)
        except asyncio.QueueFull:
            # Sem payload: o canal e o tipo bastam para medir descarte.
            LOGGER.warning(
                "realtime_queue_dropped channel=%s event_type=%s",
                item[0],
                item[1].get("type"),
            )

    def listener(received_channel: str, event: dict[str, Any]) -> None:
        if received_channel != channel or _loop is None:
            return
        _loop.call_soon_threadsafe(enqueue, (received_channel, event))

    entry = _channel_refs.get(channel)
    if entry is None:
        unregister = get_realtime_bus().register(channel, listener)
        entry = [unregister, 0]
        _channel_refs[channel] = entry
    entry[1] += 1
    released = False

    def release() -> None:
        nonlocal released
        if released:
            return
        released = True
        entry[1] -= 1
        if entry[1] == 0:
            entry[0]()
            _channel_refs.pop(channel, None)

    return release


async def _drain_events() -> None:
    while True:
        channel, raw_event = await _queue.get()  # type: ignore[union-attr]
        try:
            envelope = validate_envelope(channel, raw_event)
        except (ValidationError, ValueError) as error:
            LOGGER.warning(
                "realtime_dispatch_discarded channel=%s error_type=%s",
                channel,
                type(error).__name__,
            )
            continue
        if envelope.type == "message.created":
            message = envelope.message
            if message is None or channel != room_channel(message.room_kind, message.room_id):
                LOGGER.warning("realtime_channel_mismatch_discarded channel=%s", channel)
                continue
            await manager.broadcast(
                (message.workspace_id, message.room_kind, message.room_id),
                raw_event,
            )
        elif envelope.type == "notification.created":
            notification = envelope.notification
            if notification is None or channel != user_channel(notification.user_id):
                LOGGER.warning("realtime_channel_mismatch_discarded channel=%s", channel)
                continue
            await manager.broadcast_user(
                (notification.workspace_id, notification.user_id), raw_event
            )


async def start_event_dispatcher() -> None:
    """Chamado no lifespan: liga os eventos do barramento às conexões locais."""
    global _loop, _queue, _task
    _loop = asyncio.get_running_loop()
    _queue = asyncio.Queue(maxsize=WS_MAX_QUEUE)
    _task = asyncio.create_task(_drain_events())


async def stop_event_dispatcher() -> None:
    global _loop, _queue, _task
    for channel, entry in list(_channel_refs.items()):
        entry[0]()
        _channel_refs.pop(channel, None)
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    _loop = None
    _queue = None


def _authenticate(db: Session, token: str | None):
    claims = decode_access_claims(token or "")
    if claims is None:
        return None
    user = UserRepository(db).get_by_id(claims.user_id)
    if user is None or not user.status_ativo:
        return None
    # ADR 0003 (iii): a revogação por permission_version também vale no
    # handshake; sem a claim ou com versão divergente, a conexão é negada.
    if claims.permission_version != int(user.permission_version or 1):
        return None
    return user


def _token_deadline(token: str) -> datetime | None:
    """Vida útil da conexão ≤ expiração do JWT e ≤ ACCESS_TOKEN_EXPIRE_MINUTES."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.auth_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    token_exp = datetime.fromtimestamp(int(claims["exp"]), UTC)
    config_exp = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    return min(token_exp, config_exp)


@router.websocket("/ws/{room_kind}/{room_id}")
async def chat_room(
    websocket: WebSocket,
    room_kind: str,
    room_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Conecta em `/ws/channel/{id}` ou `/ws/conversation/{id}` com subprotocolos bearer."""
    if room_kind not in {"channel", "conversation"}:
        await websocket.close(code=4404)
        return

    # FASTAPI-WS-001: Origin é validado na app (não há proxy no repo), antes do accept.
    origin = websocket.headers.get("origin")
    if not origin or origin not in get_settings().cors_origins:
        await websocket.close(code=4403)
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
    expires_at = _token_deadline(token)
    if expires_at is None or expires_at <= datetime.now(UTC):
        await websocket.close(code=4401)
        return
    user = await run_in_threadpool(_authenticate, db, token)
    if user is None:
        # Sem token, sem e-mail/ID do usuário e sem conteúdo da mensagem.
        LOGGER.warning("websocket_auth_rejected reason=invalid_or_inactive_user")
        await websocket.close(code=4401)
        return
    try:
        room = await run_in_threadpool(authorize_room, db, room_kind, room_id, user.id)
    except NotFoundException:
        await websocket.close(code=4404)
        return
    except ForbiddenException:
        await websocket.close(code=4403)
        return

    workspace_id = room.workspace_id
    release_room = _subscribe_channel(room_channel(room_kind, room_id))
    release_user = _subscribe_channel(user_channel(user.id))
    connection = Connection(
        websocket=websocket,
        user_id=user.id,
        workspace_id=workspace_id,
        room_kind=room_kind,
        room_id=room_id,
        expires_at=expires_at,
        subprotocol="bearer",
        release_room=release_room,
        release_user=release_user,
    )
    try:
        await manager.connect((workspace_id, room_kind, room_id), connection)
    except WebSocketDisconnect:
        await manager.drop(connection, (workspace_id, room_kind, room_id), close=False)
        return

    service = build_chat_realtime_usecase(db)
    received_at: deque[float] = deque()
    try:
        while True:
            if datetime.now(UTC) >= expires_at:
                await manager.drop(connection, (workspace_id, room_kind, room_id))
                break
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except RuntimeError:
                await manager.drop(connection, (workspace_id, room_kind, room_id), close=False)
                break
            if len(raw.encode("utf-8")) > WS_MAX_FRAME_BYTES:
                await manager.drop(connection, (workspace_id, room_kind, room_id), code=4409)
                break

            now = time.monotonic()
            while received_at and now - received_at[0] > WS_RATE_WINDOW_SECONDS:
                received_at.popleft()
            if len(received_at) >= WS_RATE_MAX_MESSAGES:
                await manager.drop(connection, (workspace_id, room_kind, room_id), code=4429)
                break
            received_at.append(now)

            try:
                payload = SocketMessage.model_validate(json.loads(raw))
            except (ValidationError, ValueError, TypeError):
                await websocket.send_json(
                    {"type": "error", "message": "Formato de mensagem inválido"}
                )
                continue

            try:
                await run_in_threadpool(
                    lambda: service.create_message(
                        MessageCreate(
                            room_id=room_id,
                            room_kind=room_kind,
                            body=payload.body,
                            parent_id=payload.parent_id,
                            attachments=payload.attachments,
                            mention_ids=payload.mention_ids,
                        ),
                        user.id,
                    )
                )
            except Exception as error:
                LOGGER.warning("websocket_message_rejected error_type=%s", type(error).__name__)
                await websocket.send_json(
                    {"type": "error", "message": "Não foi possível persistir a mensagem"}
                )
    finally:
        await manager.drop(connection, (workspace_id, room_kind, room_id), close=False)
