from typing import Annotated

from app.modules.auth.deps import AdminUser, CurrentUser
from app.modules.user.deps import get_user_service
from app.modules.user.schemas.dto import (
    UserCreate,
    UserList,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.modules.user.usecases.services import UserService
from common.errors import ExceptionData, ForbiddenException
from fastapi import APIRouter, Depends, Query, Response, status

router = APIRouter(prefix="/users", tags=["users"])

Service = Annotated[UserService, Depends(get_user_service)]


def _ensure_self_or_admin(current: CurrentUser, user_id: str) -> None:
    if not current.interno_adm and current.id != user_id:
        raise ForbiddenException(
            ExceptionData(message="Acesso negado", error_code="FORBIDDEN"), is_expected=True
        )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _: AdminUser, service: Service) -> UserResponse:
    """Cria usuário (admin), podendo definir flags administrativas."""
    return UserResponse.model_validate(service.create(payload))


@router.get("", response_model=UserList)
def list_users(
    _: AdminUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_ativo: bool | None = None,
) -> UserList:
    """Lista usuários com paginação; `status_ativo` filtra, omitido traz todos."""
    users, total = service.list(skip, limit, status_ativo)
    return UserList(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, current: CurrentUser, service: Service) -> UserResponse:
    """Busca por id (admin ou o próprio usuário)."""
    _ensure_self_or_admin(current, user_id)
    return UserResponse.model_validate(service.get(user_id))


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str, payload: UserUpdate, current: CurrentUser, service: Service
) -> UserResponse:
    """Atualiza e-mail, telefone, idade e termos (admin ou o próprio usuário)."""
    _ensure_self_or_admin(current, user_id)
    return UserResponse.model_validate(service.update(user_id, payload))


@router.patch("/{user_id}/status", response_model=UserResponse)
def set_user_status(
    user_id: str, payload: UserStatusUpdate, _: AdminUser, service: Service
) -> UserResponse:
    """Ativa ou desativa o usuário (admin)."""
    return UserResponse.model_validate(service.set_status(user_id, payload.status_ativo))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, _: AdminUser, service: Service) -> Response:
    """Soft delete: desativa o usuário (admin)."""
    service.set_status(user_id, False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
