from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

CardPriority = Annotated[str | None, Field(pattern="^(baixa|media|alta|critica)$", default=None)]
CardType = Annotated[str | None, Field(pattern="^(historia|bug|tarefa|epico)$", default=None)]


class CardBase(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=200)]
    description: str | None = Field(max_length=5000, default=None)
    type: CardType = None
    priority: CardPriority = None
    assignee_id: str | None = None
    reporter_id: str | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    objective: str | None = Field(max_length=5000, default=None)
    points: int | None = Field(ge=0, le=100, default=None)
    fix_version: str | None = None
    budget_project: str | None = Field(max_length=200, default=None)
    parent_id: str | None = None


class CardCreate(CardBase):
    """Payload para criar um card. board_id e team_id são obrigatórios; columnId é ignorado."""

    board_id: str
    team_id: str
    column_id: str | None = Field(default=None, description="Ignorado: card nasce no backlog")
    labels: list[str] | None = None
    subtasks: list[dict] | None = None
    checklist: list[dict] | None = None
    custom_fields: dict | None = None


class CardUpdate(BaseModel):
    """Campos editáveis; version para otimistic locking."""

    title: str | None = Field(min_length=3, max_length=200, default=None)
    description: str | None = Field(max_length=5000, default=None)
    type: CardType = None
    priority: CardPriority = None
    assignee_id: str | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    objective: str | None = Field(max_length=5000, default=None)
    points: int | None = Field(ge=0, le=100, default=None)
    fix_version: str | None = None
    budget_project: str | None = Field(max_length=200, default=None)
    labels: list[str] | None = None
    subtasks: list[dict] | None = None
    checklist: list[dict] | None = None
    custom_fields: dict | None = None
    expected_version: int


class CardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    column_id: str | None
    team_id: str
    title: str
    description: str | None
    type: str | None
    priority: str | None
    assignee_id: str | None
    reporter_id: str | None
    due_date: datetime | None
    start_date: datetime | None
    objective: str | None
    points: int | None
    fix_version: str | None
    budget_project: str | None
    parent_id: str | None
    version: int
    is_blocked: bool
    block_reason: str | None = None
    blocked_by: str | None = None
    blocked_at: datetime | None = None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class CardList(BaseModel):
    items: list[CardResponse]
    total: int
    skip: int
    limit: int


class CardMoveInput(BaseModel):
    column_id: str
    expected_version: int


class CardBlockInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int


class CardUnblockInput(BaseModel):
    justification: str | None = Field(default=None, max_length=2000)
    expected_version: int


class CardCloneInput(BaseModel):
    pass


class CardHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    author_id: str | None
    criado_em: datetime
