"""Compatibilidade: re-exporta do novo layout modular."""

from app.modules.auth.deps import (  # noqa: F401
    AdminUser,
    CurrentUser,
    get_auth_service,
    get_current_user,
    require_admin,
)
from app.modules.auth.entrypoints.routes import router  # noqa: F401
from app.modules.auth.schemas.dto import LoginRequest, TokenResponse  # noqa: F401
from app.modules.auth.usecases.services import AuthService  # noqa: F401
from app.modules.auth.usecases.tokens import (  # noqa: F401
    create_access_token,
    decode_access_token,
)
