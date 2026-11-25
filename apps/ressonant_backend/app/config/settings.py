import os
from dataclasses import dataclass, field
from functools import lru_cache

from pydantic import SecretStr

MIN_SECRET_LENGTH = 32


class ConfigurationError(RuntimeError):
    """Configuração obrigatória ausente ou inválida."""


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    redis_url: str | None
    auth_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    cors_origins: list[str]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_from_email: str
    smtp_from_name: str
    frontend_base_url: str
    email_enabled: bool
    # Bootstrap do primeiro admin: opcionais e fora de repr (secret/PII).
    admin_name: str | None = field(default=None, repr=False)
    admin_email: str | None = field(default=None, repr=False)
    admin_password: SecretStr | None = field(default=None, repr=False)
    admin_cpf: str | None = field(default=None, repr=False)
    admin_telefone: str | None = field(default=None, repr=False)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip() or None


def _secret_optional(name: str) -> SecretStr | None:
    value = os.getenv(name)
    return SecretStr(value) if value else None


@lru_cache
def get_settings() -> Settings:
    auth_secret = _required("AUTH_SECRET")
    if len(auth_secret) < MIN_SECRET_LENGTH:
        raise ConfigurationError(f"AUTH_SECRET deve ter ao menos {MIN_SECRET_LENGTH} caracteres")

    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    return Settings(
        environment=os.getenv("ENVIRONMENT", "development"),
        database_url=_required("DATABASE_URL"),
        redis_url=os.getenv("REDIS_URL", "").strip() or None,
        auth_secret=auth_secret,
        jwt_algorithm="HS256",
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        smtp_host=smtp_host,
        smtp_port=int(os.getenv("SMTP_PORT", "1025")),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        smtp_use_tls=_bool("SMTP_USE_TLS", default=False),
        smtp_use_ssl=_bool("SMTP_USE_SSL", default=False),
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "noreply@ressonant.local").strip(),
        smtp_from_name=os.getenv("SMTP_FROM_NAME", "Ressonant").strip(),
        frontend_base_url=os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/"),
        email_enabled=_bool("EMAIL_ENABLED", default=bool(smtp_host)),
        admin_name=_optional("ADMIN_NAME"),
        admin_email=_optional("ADMIN_EMAIL"),
        admin_password=_secret_optional("ADMIN_PASSWORD"),
        admin_cpf=_optional("ADMIN_CPF"),
        admin_telefone=_optional("ADMIN_TELEFONE"),
    )
