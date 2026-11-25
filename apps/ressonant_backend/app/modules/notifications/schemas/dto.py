from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    """DTO interno: `user_id` é fixado pelo servidor, nunca aceito da rota pública."""

    user_id: str
    kind: Annotated[str, Field(min_length=1, max_length=50)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str | None, Field(max_length=200)] = None
    workspace_id: str | None = None
    actor_id: str | None = None
    message_id: str | None = None
    room_id: str | None = None
    room_kind: str | None = None


class NotificationPublicCreate(BaseModel):
    """Corpo aceito por `POST /notifications` (CYB-WS-004)."""

    model_config = ConfigDict(extra="forbid")

    kind: Annotated[str, Field(min_length=1, max_length=50)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str | None, Field(max_length=200)] = None
    workspace_id: str
    actor_id: str | None = None
    message_id: str | None = None
    room_id: str | None = None
    room_kind: Annotated[str | None, Field(pattern="^(channel|conversation)$")] = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    kind: str
    title: str
    body: str | None
    workspace_id: str | None = None
    actor_id: str | None = None
    message_id: str | None = None
    room_id: str | None = None
    room_kind: str | None = None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationResponse]
    total: int
    skip: int
    limit: int
