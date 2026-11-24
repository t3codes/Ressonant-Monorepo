from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.auth.usecases.services import (
    PUBLIC_READ_MAX_ATTEMPTS,
    PUBLIC_READ_WINDOW_SECONDS,
    _rate_limit,
)
from app.modules.organization.deps import get_invitation_service
from app.modules.organization.schemas.dto import (
    InvitationAcceptResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    InvitationPublicResponse,
    InvitationResendResponse,
    InvitationResponse,
)
from app.modules.organization.usecases.services import InvitationService
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(tags=["invitations"])
Service = Annotated[InvitationService, Depends(get_invitation_service)]


def _break_glass_reason(request: Request) -> str | None:
    return request.headers.get("x-break-glass-reason")


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InvitationCreateResponse,
    status_code=201,
)
def create_invitation(
    organization_id: str,
    payload: InvitationCreateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> InvitationCreateResponse:
    return service.create_invitation(
        organization_id,
        current_user,
        payload,
        reason=_break_glass_reason(request),
    )


@router.get(
    "/organizations/{organization_id}/invitations",
    response_model=list[InvitationResponse],
)
def list_invitations(
    organization_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> list[InvitationResponse]:
    return service.list_invitations(
        organization_id, current_user, reason=_break_glass_reason(request)
    )


@router.post(
    "/organizations/{organization_id}/invitations/{invitation_id}/resend",
    response_model=InvitationResendResponse,
)
def resend_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> InvitationResendResponse:
    return service.resend_invitation(
        organization_id,
        invitation_id,
        current_user,
        reason=_break_glass_reason(request),
    )


@router.delete(
    "/organizations/{organization_id}/invitations/{invitation_id}",
    status_code=204,
)
def delete_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> None:
    service.delete_invitation(
        organization_id,
        invitation_id,
        current_user,
        reason=_break_glass_reason(request),
    )


@router.post(
    "/organizations/{organization_id}/invitations/{invitation_id}/revoke",
    response_model=InvitationResponse,
)
def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> InvitationResponse:
    return service.revoke_invitation(
        organization_id,
        invitation_id,
        current_user,
        reason=_break_glass_reason(request),
    )


def _check_public_rate(request: Request, scope: str) -> None:
    ip = request.client.host if request.client else "unknown"
    if scope == "read":
        # BUG-T3-014: leitura tem chave e limite próprios; não consome o bucket
        # das mutações (accept/decline), que continua rígido em 5 tentativas.
        allowed, info = _rate_limit.consume(
            f"invite-read:{ip}",
            max_attempts=PUBLIC_READ_MAX_ATTEMPTS,
            window_seconds=PUBLIC_READ_WINDOW_SECONDS,
        )
    else:
        allowed, info = _rate_limit.consume(f"invite:{scope}:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde antes de tentar novamente.",
            headers={
                "RateLimit-Remaining": str(info["remaining"]),
                "RateLimit-Reset": str(info["reset"]),
            },
        )


@router.get("/invitations/{token}", response_model=InvitationPublicResponse)
def get_public_invitation(
    token: str, request: Request, service: Service
) -> InvitationPublicResponse:
    _check_public_rate(request, "read")
    return service.get_public_invitation(token)


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptResponse)
def accept_invitation(
    token: str, request: Request, service: Service, current_user: CurrentUser
) -> InvitationAcceptResponse:
    _check_public_rate(request, "accept")
    return service.accept_invitation(token, current_user)


@router.post("/invitations/{token}/decline", response_model=InvitationResponse)
def decline_invitation(token: str, request: Request, service: Service) -> InvitationResponse:
    _check_public_rate(request, "decline")
    return service.decline_invitation(token)
