from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Slug = Annotated[str, Field(min_length=3, max_length=100)]
Name = Annotated[str, Field(min_length=3, max_length=100)]
Description = Annotated[str | None, Field(max_length=500, default=None)]


class BoardBase(BaseModel):
    name: Name
    slug: Slug
    description: Description


class BoardCreate(BoardBase):
    """Payload para criar um board. workspace_id e team_id são obrigatórios."""

    workspace_id: str
    team_id: str


class BoardUpdate(BaseModel):
    """Campos editáveis; workspace_id, team_id e slug não mudam após a criação."""

    name: Name | None = None
    description: Description = None
    status_ativo: bool | None = None


class BoardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    team_id: str
    name: str
    slug: str
    description: str | None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class BoardList(BaseModel):
    items: list[BoardResponse]
    total: int
    skip: int
    limit: int


class BoardStatusUpdate(BaseModel):
    status_ativo: bool


class BoardColumnBase(BaseModel):
    name: Name
    slug: Slug
    position: Annotated[int, Field(ge=0, default=0)]
    wip_limit: Annotated[int | None, Field(ge=1, default=None)] = None


class BoardColumnCreate(BoardColumnBase):
    pass


class BoardColumnUpdate(BaseModel):
    name: Name | None = None
    slug: Slug | None = None
    wip_limit: Annotated[int | None, Field(ge=1)] = None


class BoardColumnReorderInput(BaseModel):
    ordered_column_ids: list[str] = Field(min_length=1)


class BoardColumnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    name: str
    slug: str
    position: int
    wip_limit: int | None
    created_at: datetime


class BoardColumnList(BaseModel):
    items: list[BoardColumnResponse]
    total: int
