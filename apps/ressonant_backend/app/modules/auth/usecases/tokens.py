from datetime import UTC, datetime, timedelta

import jwt
from app.config.settings import get_settings


def create_access_token(user_id: str) -> tuple[str, int]:
    """Cria um access token JWT com claims sub, type, iat, exp."""
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, settings.auth_secret, algorithm=settings.jwt_algorithm), expires_in


def decode_access_token(token: str) -> str | None:
    """Retorna o user_id do token ou None se inválido/expirado."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.auth_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("type") != "access":
        return None
    return claims["sub"]
