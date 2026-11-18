from typing import Annotated

from app.modules.auth.deps import CurrentUser, get_auth_service
from app.modules.auth.schemas.dto import LoginRequest, TokenResponse
from app.modules.auth.usecases.services import AuthService
from app.modules.user.deps import get_user_service
from app.modules.user.schemas import UserRegister, UserResponse
from app.modules.user.usecases.services import UserService
from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserRegister,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Cadastro público de usuário comum."""
    return UserResponse.model_validate(service.register(payload))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Autentica por e-mail e senha e devolve o access token."""
    token, expires_in = service.login(payload.email, payload.senha)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Dados do usuário autenticado."""
    return UserResponse.model_validate(user)
