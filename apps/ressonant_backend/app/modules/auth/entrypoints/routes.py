from typing import Annotated

from app.modules.auth.deps import CurrentUser, get_auth_service
from app.modules.auth.schemas.dto import LoginRequest, TokenResponse
from app.modules.auth.usecases.services import AuthService
from app.modules.user.deps import get_user_service
from app.modules.user.schemas import UserRegister, UserResponse
from app.modules.user.usecases.services import UserService
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

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
    request: Request,
) -> TokenResponse:
    """Autentica por e-mail e senha e devolve o access token."""
    ip = request.client.host if request.client else "unknown"
    allowed, limit_info = service.check_rate_limit(ip)

    if not allowed:
        headers = {
            "RateLimit-Remaining": str(limit_info["remaining"]),
            "RateLimit-Reset": str(limit_info["reset"]),
        }
        return JSONResponse(
            content={
                "status_code": 429,
                "message": "Muitas tentativas de login. Tente novamente mais tarde.",
            },
            status_code=429,
            headers=headers,
        )

    token, expires_in = service.login(payload.email, payload.senha)
    service.clear_rate_limit(ip)
    headers = {
        "RateLimit-Remaining": str(limit_info["remaining"]),
        "RateLimit-Reset": str(limit_info["reset"]),
    }
    return JSONResponse(
        content=TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in,
        ).model_dump(),
        status_code=200,
        headers=headers,
    )


@router.post("/logout", response_model=dict)
def logout(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    _user: CurrentUser,
) -> dict:
    """Invalidar token de acesso ao fazer logout."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    result = service.logout(token)
    return result


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Dados do usuário autenticado."""
    return UserResponse.model_validate(user)
