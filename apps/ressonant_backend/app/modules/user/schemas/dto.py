from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Password = Annotated[str, Field(min_length=8, max_length=128)]
Age = Annotated[int, Field(ge=18, le=120)]


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_valid_cpf(cpf: str) -> bool:
    """Valida CPF (11 dígitos, dígitos verificadores, sem sequência repetida)."""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(d) * w for d, w in zip(cpf[:size], range(size + 1, 1, -1), strict=True))
        if int(cpf[size]) != (total * 10 % 11) % 10:
            return False
    return True


class _UserIdentity(BaseModel):
    email: EmailStr
    cpf: str = Field(description="CPF com ou sem máscara; armazenado só com dígitos")
    telefone: str = Field(description="Telefone com DDD (10 ou 11 dígitos)")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, value: str) -> str:
        cleaned = _digits(value)
        if not is_valid_cpf(cleaned):
            raise ValueError("CPF inválido")
        return cleaned

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, value: str) -> str:
        cleaned = _digits(value)
        if len(cleaned) not in (10, 11):
            raise ValueError("Telefone deve ter 10 ou 11 dígitos")
        return cleaned


class UserRegister(_UserIdentity):
    """Cadastro público: nunca define flags administrativas."""

    senha: Password
    idade: Age
    termos_contrato: bool

    @field_validator("termos_contrato")
    @classmethod
    def must_accept_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("É necessário aceitar os termos do contrato")
        return value


class UserCreate(UserRegister):
    """Criação por administrador."""

    status_ativo: bool = True
    # Contrato publicado mantido por compatibilidade; a rota rejeita `true`
    # com 403 ADMIN_FLAG_NOT_ALLOWED. Promoção real: /admin/superusers.
    interno_adm: bool = Field(
        default=False,
        description="Somente-leitura: envie sempre false; use /admin/superusers para promover.",
    )


class UserUpdate(BaseModel):
    """Campos editáveis; senha, CPF e flags administrativas ficam fora."""

    email: EmailStr
    telefone: str
    idade: Age
    termos_contrato: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("telefone")
    @classmethod
    def validate_telefone(cls, value: str) -> str:
        cleaned = _digits(value)
        if len(cleaned) not in (10, 11):
            raise ValueError("Telefone deve ter 10 ou 11 dígitos")
        return cleaned


class UserStatusUpdate(BaseModel):
    status_ativo: bool


class UserAdminUpdate(BaseModel):
    interno_adm: bool


class UserResponse(BaseModel):
    """Contrato de resposta: a migration 0020 permite telefone/idade NULL.

    O aceite por convite persiste ambos como NULL quando omitidos; torná-los
    opcionais aqui faz `/auth/me` e `/me/context` carregarem a sessão sem
    duplicar schema. `_UserIdentity`, `UserRegister` e `UserUpdate` continuam
    exigindo os campos na entrada (CYB-006).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    cpf: str
    telefone: str | None = None
    idade: int | None = None
    termos_contrato: bool
    status_ativo: bool
    interno_adm: bool
    name: str | None = None
    title: str | None = None
    avatar_url: str | None = None
    avatar_content_type: str | None = None
    avatar_size_bytes: int | None = None
    criado_em: datetime
    atualizado_em: datetime


class InvitedUserResponse(UserResponse):
    """Resposta do aceite por convite (CYB-003; mantido por compatibilidade).

    Após BE-04, `UserResponse` já admite `telefone`/`idade` nulos — este alias
    não adiciona regra nova e existe apenas para não quebrar o contrato do
    201 publicado no ciclo anterior.
    """

    telefone: str | None = None
    idade: int | None = None


class UserList(BaseModel):
    items: list[UserResponse]
    total: int
    skip: int
    limit: int
