import uuid
from datetime import datetime

from app.database.engine import Base
from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    recipient_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    cc_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    bcc_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    forwarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
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
