import uuid
from datetime import datetime

from app.database.engine import Base
from sqlalchemy import Boolean, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    corporate_email: Mapped[str | None] = mapped_column(
        String(254), unique=True, index=True, nullable=True
    )
    personal_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    cpf: Mapped[str] = mapped_column(String(11), unique=True)
    idade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permission_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    termos_contrato: Mapped[bool] = mapped_column(Boolean, default=False)
    telefone: Mapped[str | None] = mapped_column(String(11), nullable=True)
    status_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    interno_adm: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
