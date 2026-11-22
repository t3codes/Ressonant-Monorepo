from typing import Literal

from app.modules.billing.schemas.dto import SubscriptionResponse
from app.modules.user.schemas.dto import UserRegister, UserResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    token: str


class OrganizacaoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=2, max_length=100)
    slug: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class ConvidadoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"
    nome: str | None = None


class RegistrationCreate(UserRegister):
    """Payload aditivo do cadastro atômico (§5.1 do plano)."""

    model_config = ConfigDict(extra="forbid")

    nome_completo: str = Field(min_length=2, max_length=60)
    cargo: str = Field(min_length=2, max_length=100)
    organizacao: OrganizacaoInput
    plano_id: Literal["inicial", "equipe", "empresa"]
    trial: Literal[True] = True
    workspace_nome: str = Field(min_length=3, max_length=100)
    equipe_inicial_nome: str = Field(min_length=3, max_length=100)
    convidados: list[ConvidadoInput] = Field(default_factory=list, max_length=50)

    @field_validator("nome_completo")
    @classmethod
    def must_have_two_words(cls, value: str) -> str:
        if len(value.split()) < 2:
            raise ValueError("nome_completo deve ter ao menos duas palavras")
        return value

    @field_validator("convidados")
    @classmethod
    def unique_emails(cls, value: list[ConvidadoInput]) -> list[ConvidadoInput]:
        emails = [convidado.email.lower() for convidado in value]
        if len(emails) != len(set(emails)):
            raise ValueError("convidados não pode repetir e-mails")
        return value


class OrganizacaoResponse(BaseModel):
    id: str
    nome: str
    slug: str
    role: str = "owner"


class SeatsResponse(BaseModel):
    plan_code: str
    limit: int | None
    used: int


class RegistrationResponse(BaseModel):
    user: UserResponse
    organizacao: OrganizacaoResponse
    assinatura: SubscriptionResponse
    workspace_ids: list[str]
    workspace_inicial_id: str
    equipe_inicial_id: str
    seats: SeatsResponse
    member_ids: list[str]
