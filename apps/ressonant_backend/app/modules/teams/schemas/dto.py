from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Slug = Annotated[str, Field(min_length=3, max_length=100)]
Name = Annotated[str, Field(min_length=3, max_length=100)]
Description = Annotated[str | None, Field(max_length=500, default=None)]


class TeamBase(BaseModel):
    name: Name
    slug: Slug
    description: Description


class TeamCreate(TeamBase):
    """Payload para criar um team. workspace_id é obrigatório; owner_id vem do JWT."""

    workspace_id: str


class TeamUpdate(BaseModel):
    """Campos editáveis; workspace_id e slug não mudam após a criação."""

    name: Name | None = None
    description: Description = None
    status_ativo: bool | None = None


class TeamMemberAdd(BaseModel):
    user_id: str
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    user_id: str
    role: str
    criado_em: datetime


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    workspace_id: str
    owner_id: str
    description: str | None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class TeamList(BaseModel):
    items: list[TeamResponse]
    total: int
    skip: int
    limit: int


class TeamStatusUpdate(BaseModel):
    status_ativo: bool
