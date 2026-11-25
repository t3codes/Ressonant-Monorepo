from datetime import datetime
from typing import Annotated, Any

from app.modules.user.schemas.dto import is_valid_cpf
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BillingCycle = Annotated[str, Field(pattern=r"^(monthly|yearly|custom)$")]


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def mask_cpf(cpf: str) -> str:
    """Nunca devolve os nove primeiros dígitos do CPF."""
    digits = _digits(cpf)
    return f"***.***.***-{digits[-2:]}" if len(digits) == 11 else "***.***.***-**"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StrictOut(_Strict):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SuperuserSummary(_StrictOut):
    id: str
    nome: str | None = None
    email: str
    cpf_masked: str
    telefone: str | None = None
    status_ativo: bool
    interno_adm: bool
    permission_version: int
    # `server_default` só é materializado após o INSERT; na resposta da mesma
    # requisição o valor pode ainda não estar carregado.
    criado_em: datetime | None = None


class SuperuserCreate(_Strict):
    nome: str = Field(min_length=2, max_length=100)
    email: EmailStr
    cpf: str = Field(description="CPF com ou sem máscara; armazenado só com dígitos")
    telefone: str = Field(description="Telefone com DDD (10 ou 11 dígitos)")
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="Obrigatória apenas quando o e-email ainda não existe",
    )

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


class PlanResponse(_StrictOut):
    id: str
    code: str
    name: str
    billing_cycle: str
    base_price_cents: int
    price_per_seat_cents: int
    included_seats: int
    limits: dict[str, Any]
    is_public: bool
    is_active: bool
    # Colunas legadas: billing atual continua lendo-as.
    price_cents: int
    currency: str
    seat_limit: int | None = None
    overage_cents_per_seat: int | None = None
    trial_days: int
    active: bool


class PlanCreate(_Strict):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=100)
    billing_cycle: BillingCycle = "monthly"
    base_price_cents: int = Field(ge=0, default=0)
    price_per_seat_cents: int = Field(ge=0, default=0)
    included_seats: int = Field(ge=0, default=0)
    limits: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = True
    is_active: bool = True
    price_cents: int | None = Field(
        default=None, ge=0, description="Legado; default=base_price_cents"
    )
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    seat_limit: int | None = Field(default=None, ge=0, description="Legado; default=included_seats")
    overage_cents_per_seat: int | None = Field(
        default=None, ge=0, description="Legado; default=price_per_seat_cents"
    )
    trial_days: int = Field(default=14, ge=0, le=365)


class PlanUpdate(_Strict):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    billing_cycle: BillingCycle | None = None
    base_price_cents: int | None = Field(default=None, ge=0)
    price_per_seat_cents: int | None = Field(default=None, ge=0)
    included_seats: int | None = Field(default=None, ge=0)
    limits: dict[str, Any] | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    seat_limit: int | None = Field(default=None, ge=0)
    overage_cents_per_seat: int | None = Field(default=None, ge=0)
    trial_days: int | None = Field(default=None, ge=0, le=365)
    active: bool | None = None


class SystemSettingResponse(_StrictOut):
    key: str
    value: dict[str, Any]
    description: str | None = None
    updated_by: str | None = None
    updated_at: datetime


class SystemSettingUpdate(_Strict):
    value: dict[str, Any]
    description: str | None = None
