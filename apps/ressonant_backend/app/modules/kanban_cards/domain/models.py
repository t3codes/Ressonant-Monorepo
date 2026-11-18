import uuid
from datetime import datetime

from app.database.engine import Base
from app.modules.kanban_boards.domain.models import Board
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    board_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("boards.id"), nullable=False, index=True
    )
    column_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("board_columns.id"), nullable=True, index=True
    )
    team_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    reporter_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fix_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget_project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
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

    board: Mapped["Board"] = relationship("Board")
    subtasks: Mapped[list["CardSubtask"]] = relationship(
        "CardSubtask", back_populates="card", cascade="all, delete-orphan"
    )
    checklist_items: Mapped[list["CardChecklist"]] = relationship(
        "CardChecklist", back_populates="card", cascade="all, delete-orphan"
    )
    comments: Mapped[list["CardComment"]] = relationship(
        "CardComment", back_populates="card", cascade="all, delete-orphan"
    )
    history: Mapped[list["CardHistory"]] = relationship(
        "CardHistory", back_populates="card", cascade="all, delete-orphan"
    )
    worklogs: Mapped[list["CardWorklog"]] = relationship(
        "CardWorklog", back_populates="card", cascade="all, delete-orphan"
    )
    links: Mapped[list["CardLink"]] = relationship(
        "CardLink", back_populates="card", cascade="all, delete-orphan"
    )
    watchers: Mapped[list["CardWatcher"]] = relationship(
        "CardWatcher", back_populates="card", cascade="all, delete-orphan"
    )
    custom_fields: Mapped[list["CardCustomField"]] = relationship(
        "CardCustomField", back_populates="card", cascade="all, delete-orphan"
    )


class CardSubtask(Base):
    __tablename__ = "card_subtasks"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)  # PTA-97.1, PTA-97.2...
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="todo", nullable=False)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="subtasks")


class CardChecklist(Base):
    __tablename__ = "card_checklist"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="checklist_items")


class CardComment(Base):
    __tablename__ = "card_comments"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="comments")


class CardHistory(Base):
    __tablename__ = "card_history"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # created, updated, moved, etc.
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="history")


class CardWorklog(Base):
    __tablename__ = "card_worklogs"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    time_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="worklogs")


class CardLink(Base):
    __tablename__ = "card_links"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="links")


class CardWatcher(Base):
    __tablename__ = "card_watchers"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="watchers")


class CardCustomField(Base):
    __tablename__ = "card_custom_fields"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    card_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped["Card"] = relationship("Card", back_populates="custom_fields")
