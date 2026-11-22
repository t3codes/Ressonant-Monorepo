from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.organization.deps import get_invitation_service
from app.modules.organization.schemas.dto import (
    InvitationAcceptResponse,
    InvitationCreateRequest,
    InvitationCreateResponse,
    InvitationResponse,
)
from app.modules.organization.usecases.services import InvitationService
from fastapi import APIRouter, Depends, Request

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


@router.delete(
    "/organizations/{organization_id}/invitations/{invitation_id}",
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


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptResponse)
def accept_invitation(
    token: str,
    service: Service,
    current_user: CurrentUser,
) -> InvitationAcceptResponse:
    return service.accept_invitation(token, current_user)
