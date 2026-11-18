"""Compatibilidade: re-exporta do novo layout modular."""

from app.modules.user.dataproviders.repository import UserRepository  # noqa: F401
from app.modules.user.deps import get_user_repository, get_user_service  # noqa: F401
from app.modules.user.domain.models import User  # noqa: F401
from app.modules.user.entrypoints.routes import router  # noqa: F401
from app.modules.user.schemas.dto import (  # noqa: F401
    UserCreate,
    UserList,
    UserRegister,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.modules.user.usecases.services import UserService  # noqa: F401
