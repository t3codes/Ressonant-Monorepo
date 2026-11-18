from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Slug = Annotated[str, Field(min_length=3, max_length=100)]
Name = Annotated[str, Field(min_length=3, max_length=100)]
Description = Annotated[str | None, Field(max_length=500, default=None)]


class WorkspaceBase(BaseModel):
    name: Name
    slug: Slug
    description: Description


class WorkspaceCreate(WorkspaceBase):
    """Payload para criar um workspace. owner_id é extraído do JWT, nunca do body."""


class WorkspaceUpdate(BaseModel):
    """Campos editáveis; owner_id e slug não mudam após a criação."""

    name: Name | None = None
    description: Description = None
    status_ativo: bool | None = None


class WorkspaceMemberAdd(BaseModel):
    user_id: str
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")


class WorkspaceStatusUpdate(BaseModel):
    status_ativo: bool


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    role: str
    criado_em: datetime


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    owner_id: str
    description: str | None
    status_ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class WorkspaceList(BaseModel):
    items: list[WorkspaceResponse]
    total: int
    skip: int
    limit: int
