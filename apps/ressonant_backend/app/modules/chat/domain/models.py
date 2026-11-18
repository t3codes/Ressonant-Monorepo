import uuid
from datetime import datetime

from app.database.engine import Base
from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    member_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array de user_ids
    created_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    status_ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    member_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array de user_ids
    status_ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    room_kind: Mapped[str] = mapped_column(String(20), nullable=False)  # channel | conversation
    author_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    mention_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    status_ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
