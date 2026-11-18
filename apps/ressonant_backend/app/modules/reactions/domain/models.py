import uuid
from datetime import datetime

import sqlalchemy as sa
from app.database.engine import Base
from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    message_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),)
