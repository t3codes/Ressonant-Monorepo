"""Barramento de eventos de tempo real: fan-out local e pub/sub Redis entre réplicas.

Publicador confiável: somente código do backend com `AUTH_SECRET` pode assinar
eventos. A assinatura cobre canal + envelope; Redis é transporte, não fonte de
confiança. Nenhum segredo é gravado em arquivo versionado ou configurado por
variável nova (a chave é derivada de `AUTH_SECRET`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal

import redis
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config.settings import get_settings

LOGGER = logging.getLogger(__name__)

CHANNEL_PREFIX = "ressonant:realtime:"
SIGNATURE_KEY_DOMAIN = b"ressonant:realtime:v1:hmac-key"
SIGNATURE_MESSAGE_DOMAIN = b"ressonant:realtime:v1:event"

Listener = Callable[[str, dict[str, Any]], None]


class MessageEventData(BaseModel):
    """Campos de roteamento de `message.created` (o restante do payload é ignorado)."""

    model_config = ConfigDict(extra="ignore")

    room_kind: Literal["channel", "conversation"]
    room_id: str
    workspace_id: str


class NotificationEventData(BaseModel):
    """Campos de roteamento de `notification.created`."""

    model_config = ConfigDict(extra="ignore")

    user_id: str
    workspace_id: str


class RealtimeEnvelope(BaseModel):
    """Envelope validado antes de qualquer entrega (ADR 0001: snake_case)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["message.created", "notification.created"]
    event_id: str
    occurred_at: datetime
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    message: MessageEventData | None = None
    notification: NotificationEventData | None = None

    @model_validator(mode="after")
    def _payload_matches_type(self) -> RealtimeEnvelope:
        if self.type == "message.created" and self.message is None:
            raise ValueError("message.created exige o campo message")
        if self.type == "notification.created" and self.notification is None:
            raise ValueError("notification.created exige o campo notification")
        return self


def room_channel(room_kind: str, room_id: str) -> str:
    return f"{CHANNEL_PREFIX}room:{room_kind}:{room_id}"


def user_channel(user_id: str) -> str:
    return f"{CHANNEL_PREFIX}user:{user_id}"


def new_event(event_type: str, payload_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Envelope comum: identificador para deduplicação no cliente."""
    return {
        "type": event_type,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        payload_key: payload,
    }


@lru_cache(maxsize=4)
def _signing_key(secret: str) -> bytes:
    """Separação de domínio: a chave WS nunca é a chave JWT em si."""
    return hmac.new(secret.encode("utf-8"), SIGNATURE_KEY_DOMAIN, hashlib.sha256).digest()


def _canonical_message(channel: str, event: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in event.items() if key != "signature"}
    body = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return SIGNATURE_MESSAGE_DOMAIN + b"|" + channel.encode("utf-8") + b"|" + body.encode("utf-8")


def sign_event(channel: str, event: dict[str, Any]) -> dict[str, Any]:
    """Assina canal + envelope com HMAC-SHA256 derivado de AUTH_SECRET."""
    mac = hmac.new(
        _signing_key(get_settings().auth_secret),
        _canonical_message(channel, event),
        hashlib.sha256,
    ).hexdigest()
    return {**event, "signature": mac}


def verify_event(channel: str, event: dict[str, Any]) -> bool:
    """Verifica a assinatura antes de entregar, inclusive no fan-out local."""
    provided = event.get("signature")
    if not isinstance(provided, str):
        return False
    expected = sign_event(
        channel, {key: value for key, value in event.items() if key != "signature"}
    )["signature"]
    return hmac.compare_digest(provided, expected)


def validate_envelope(channel: str, event: dict[str, Any]) -> RealtimeEnvelope:
    """Valida envelope com Pydantic e exige assinatura válida para o canal."""
    envelope = RealtimeEnvelope.model_validate(event)
    if not verify_event(channel, event):
        raise ValueError("invalid realtime signature")
    return envelope


class RealtimeBus:
    """Publica eventos assinados e valida tudo que entrega aos listeners locais."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None
        self._pubsub: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._listeners: dict[str, set[Listener]] = {}
        self._lock = threading.Lock()
        if redis_url:
            try:
                self._client = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                )
            except Exception as error:
                LOGGER.warning("realtime_redis_init_failed error_type=%s", type(error).__name__)
                self._client = None

    @property
    def distributed(self) -> bool:
        return self._client is not None

    def register(self, channel: str, listener: Listener) -> Callable[[], None]:
        """Registra um listener local e devolve a função de cancelamento."""
        with self._lock:
            self._listeners.setdefault(channel, set()).add(listener)

        def unregister() -> None:
            with self._lock:
                listeners = self._listeners.get(channel)
                if listeners is None:
                    return
                listeners.discard(listener)
                if not listeners:
                    self._listeners.pop(channel, None)

        return unregister

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        """Publica uma vez; Redis entrega também a esta réplica (sem dupla entrega)."""
        try:
            signed = sign_event(channel, event)
        except Exception as error:
            LOGGER.warning("realtime_sign_failed error_type=%s", type(error).__name__)
            return
        if self._client is not None:
            try:
                self._client.publish(
                    channel,
                    json.dumps(signed, default=str, ensure_ascii=False),
                )
                return
            except Exception as error:
                LOGGER.warning(
                    "realtime_redis_publish_failed_using_local_fanout error_type=%s",
                    type(error).__name__,
                )
        self._deliver(channel, signed)

    def start(self) -> None:
        if self._client is None or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listen_loop, name="realtime-redis-listener", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except Exception as error:
                LOGGER.debug("realtime_pubsub_close_failed error_type=%s", type(error).__name__)
            self._pubsub = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception as error:
                LOGGER.debug("realtime_redis_close_failed error_type=%s", type(error).__name__)

    def _deliver(self, channel: str, event: dict[str, Any]) -> None:
        """Nada é entregue sem envelope válido e assinatura válida para o canal."""
        try:
            validate_envelope(channel, event)
        except (ValidationError, ValueError) as error:
            LOGGER.warning(
                "realtime_invalid_event_discarded channel=%s error_type=%s",
                channel,
                type(error).__name__,
            )
            return
        with self._lock:
            listeners = tuple(self._listeners.get(channel, ()))
        for listener in listeners:
            try:
                listener(channel, event)
            except Exception as error:
                LOGGER.warning(
                    "realtime_listener_failed channel=%s error_type=%s",
                    channel,
                    type(error).__name__,
                )

    def _listen_loop(self) -> None:
        while not self._stop.is_set():
            pubsub: Any = None
            try:
                pubsub = self._client.pubsub(ignore_subscribe_messages=True)
                pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
                self._pubsub = pubsub
                for message in pubsub.listen():
                    if self._stop.is_set():
                        break
                    if message.get("type") != "pmessage":
                        continue
                    channel = str(message["channel"])
                    try:
                        event = json.loads(message["data"])
                        if not isinstance(event, dict):
                            raise ValueError("event is not an object")
                    except (TypeError, ValueError):
                        LOGGER.warning("realtime_invalid_json_discarded channel=%s", channel)
                        continue
                    self._deliver(channel, event)
            except Exception as error:
                if not self._stop.is_set():
                    LOGGER.warning(
                        "realtime_listener_loop_retrying error_type=%s", type(error).__name__
                    )
            finally:
                if pubsub is not None:
                    try:
                        pubsub.close()
                    except Exception as error:
                        LOGGER.debug(
                            "realtime_pubsub_close_failed error_type=%s",
                            type(error).__name__,
                        )
                    self._pubsub = None
            if not self._stop.is_set():
                self._stop.wait(1.0)


@lru_cache(maxsize=1)
def get_realtime_bus() -> RealtimeBus:
    return RealtimeBus(get_settings().redis_url)
