import os
from dataclasses import dataclass
from functools import lru_cache

MIN_SECRET_LENGTH = 32


class ConfigurationError(RuntimeError):
    """Configuração obrigatória ausente ou inválida."""


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    auth_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    cors_origins: list[str]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


@lru_cache
def get_settings() -> Settings:
    auth_secret = _required("AUTH_SECRET")
    if len(auth_secret) < MIN_SECRET_LENGTH:
        raise ConfigurationError(f"AUTH_SECRET deve ter ao menos {MIN_SECRET_LENGTH} caracteres")

    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return Settings(
        environment=os.getenv("ENVIRONMENT", "development"),
        database_url=_required("DATABASE_URL"),
        auth_secret=auth_secret,
        jwt_algorithm="HS256",
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
    )
