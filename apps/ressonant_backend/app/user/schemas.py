"""Compatibilidade: re-exporta do novo layout modular."""

from app.modules.user.schemas.dto import (  # noqa: F401
    Age,
    Password,
    UserCreate,
    UserList,
    UserRegister,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
    is_valid_cpf,
)
