import uuid
from datetime import datetime

from app.database.engine import Base
from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class AppNotification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # invite | card_reminder | mention | thread_reply | system | etc
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Contexto do chat (WS-PRO): colunas nullable para preservar notificações antigas.
    workspace_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    message_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    room_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    room_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
