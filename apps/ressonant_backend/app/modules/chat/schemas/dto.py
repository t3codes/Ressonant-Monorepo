from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ChannelBase(BaseModel):
    workspace_id: str
    name: Annotated[str, Field(min_length=3, max_length=100)]
    topic: str | None = Field(max_length=500, default=None)
    visibility: Annotated[str, Field(pattern="^(public|private)$", default="public")] = "public"
    member_ids: Any | None = None


class ChannelCreate(BaseModel):
    workspace_id: str
    name: Annotated[str, Field(min_length=3, max_length=100)]
    topic: str | None = Field(max_length=500, default=None)
    visibility: Annotated[str, Field(pattern="^(public|private)$", default="public")] = "public"
    member_ids: Any | None = None


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    slug: str
    topic: str | None
    visibility: str
    member_ids: Any
    created_by: str
    status_ativo: bool
    criado_em: datetime


class ChannelList(BaseModel):
    items: list[ChannelResponse]
    total: int
    skip: int
    limit: int


class ConversationBase(BaseModel):
    workspace_id: str
    member_ids: Any | None = None


class ConversationCreate(ConversationBase):
    pass


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    member_ids: Any
    status_ativo: bool
    criado_em: datetime


class ConversationList(BaseModel):
    items: list[ConversationResponse]
    total: int
    skip: int
    limit: int


class MessageCreate(BaseModel):
    """DTO público: autor e workspace nunca vêm do cliente (CYB-WS-001)."""

    model_config = ConfigDict(extra="forbid")

    room_id: str
    room_kind: Annotated[str, Field(pattern="^(channel|conversation)$")]
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    parent_id: str | None = None
    attachments: Annotated[list[dict] | None, Field(max_length=10)] = None
    mention_ids: Annotated[list[str] | None, Field(max_length=50)] = None


class MessageInput(MessageCreate):
    """DTO interno: campos derivados pelo servidor a partir do usuário e da sala."""

    workspace_id: str
    author_id: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    room_id: str
    room_kind: str
    author_id: str
    body: str
    parent_id: str | None
    attachments: str | None
    mention_ids: str | None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class MessageList(BaseModel):
    items: list[MessageResponse]
    total: int
    skip: int
    limit: int


class MessageUpdate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    mention_ids: list[str] | None = None
