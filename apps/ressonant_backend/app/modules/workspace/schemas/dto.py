from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Slug = Annotated[str, Field(min_length=3, max_length=100)]
Name = Annotated[str, Field(min_length=3, max_length=100)]
Description = Annotated[str | None, Field(max_length=500, default=None)]


class WorkspaceBase(BaseModel):
    name: Name
    slug: Slug
    description: Description


class WorkspaceCreate(WorkspaceBase):
    """Payload para criar um workspace. owner_id é extraído do JWT, nunca do body.

    organization_id é opcional: quando omisso, o service resolve a única
    organização elegível do ator. Quando informado, é validado no servidor.
    """

    organization_id: str | None = None


class WorkspaceUpdate(BaseModel):
    """Campos editáveis; owner_id e slug não mudam após a criação."""

    name: Name | None = None
    description: Description = None
    status_ativo: bool | None = None


class WorkspaceMemberAdd(BaseModel):
    """Adiciona membro por e-mail exato (preferencial) ou user_id."""

    user_id: str | None = None
    email: EmailStr | None = None
    role: str = Field(default="member", pattern="^(admin|member)$")

    @model_validator(mode="after")
    def _require_identifier(self) -> "WorkspaceMemberAdd":
        if not self.user_id and not self.email:
            raise ValueError("Informe user_id ou email")
        return self


class WorkspaceMemberUpdate(BaseModel):
    # "owner" transfere a propriedade do workspace para o membro alvo.
    role: str = Field(pattern="^(owner|admin|member)$")


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    role: str
    criado_em: datetime


class WorkspaceMemberList(BaseModel):
    items: list[WorkspaceMemberResponse]
    total: int


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    owner_id: str
    description: str | None
    status_ativo: bool
    logo_url: str | None = None
    logo_content_type: str | None = None
    logo_size_bytes: int | None = None
    criado_em: datetime
    atualizado_em: datetime


class WorkspaceList(BaseModel):
    items: list[WorkspaceResponse]
    total: int
    skip: int
    limit: int


class WorkspaceStatusUpdate(BaseModel):
    status_ativo: bool
