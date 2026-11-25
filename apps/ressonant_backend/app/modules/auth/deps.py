from typing import Annotated

from app.database.engine import get_db
from app.modules.auth.usecases.registration import RegistrationService
from app.modules.auth.usecases.services import AuthService
from app.modules.auth.usecases.tokens import decode_access_claims
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from common.errors import ExceptionData, ForbiddenException, UnauthorizedException
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(UserRepository(db))


def get_registration_service(db: Annotated[Session, Depends(get_db)]) -> RegistrationService:
    return RegistrationService(db)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Get current user, checking token blacklist."""
    unauthorized = UnauthorizedException(
        ExceptionData(message="Token ausente ou inválido", error_code="INVALID_TOKEN"),
        is_expected=True,
    )
    if credentials is None:
        raise unauthorized
    token = credentials.credentials
    service = get_auth_service(db)
    if service.is_token_blacklisted(token):
        raise unauthorized
    claims = decode_access_claims(token)
    if claims is None:
        raise unauthorized
    user = UserRepository(db).get_by_id(claims.user_id)
    if user is None or not user.status_ativo:
        raise unauthorized
    # Invalidação de sessão: token antigo deixa de valer quando a versão de
    # permissões do usuário muda (ver AuditEvent de interno_adm/status).
    if claims.permission_version != int(user.permission_version or 1):
        raise unauthorized
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.interno_adm:
        raise ForbiddenException(
            ExceptionData(message="Acesso restrito a administradores", error_code="FORBIDDEN"),
            is_expected=True,
        )
    return user


def require_platform_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Guarda das rotas /admin/*: somente superuser interno ativo."""
    if not user.interno_adm or not user.status_ativo:
        raise ForbiddenException(
            ExceptionData(
                message="Acesso restrito a administradores da plataforma",
                error_code="PLATFORM_ADMIN_REQUIRED",
            ),
            is_expected=True,
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
PlatformAdmin = Annotated[User, Depends(require_platform_admin)]
