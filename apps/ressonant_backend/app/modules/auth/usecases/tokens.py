from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from app.config.settings import get_settings


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """Claims de um access token que participam da invalidação de sessão."""

    user_id: str
    permission_version: int


# ADR 0003 (iii): nome canônico da claim. `pv` foi considerado no pré-parecer
# CYB-006, mas a decisão formal fixou `perm_version`.
PERMISSION_VERSION_CLAIM = "perm_version"


def create_access_token(user_id: str, *, permission_version: int = 1) -> tuple[str, int]:
    """Cria access token JWT com sub, type, iat, exp e `perm_version`.

    `perm_version` espelha `users.permission_version`. O DB já é recarregado a
    cada requisição; a claim acrescenta a invalidação explícita de tokens
    emitidos antes de uma mudança de permissão. O default 1 existe apenas para
    o caminho de refresh legado; o login informa sempre a versão corrente.
    """
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        PERMISSION_VERSION_CLAIM: permission_version,
    }
    return jwt.encode(claims, settings.auth_secret, algorithm=settings.jwt_algorithm), expires_in


def decode_access_claims(token: str) -> AccessClaims | None:
    """Decodifica o access token; token sem `perm_version` é rejeitado (fail closed).

    ADR 0003 (iii): tokens emitidos antes da claim não são aceitos após o
    deploy. Não há fallback para versão 1, que permitiria sessões antigas
    sobreviverem a uma revogação. JWTs de refresh não autenticam requisições.
    """
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.auth_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", PERMISSION_VERSION_CLAIM]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("type") != "access":
        return None
    user_id = claims.get("sub")
    version = claims.get(PERMISSION_VERSION_CLAIM)
    if not isinstance(user_id, str) or not user_id:
        return None
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return None
    return AccessClaims(user_id=user_id, permission_version=version)


def decode_access_token(token: str) -> str | None:
    """Compatibilidade: retorna o user_id do access token ou None se inválido."""
    claims = decode_access_claims(token)
    return claims.user_id if claims is not None else None
