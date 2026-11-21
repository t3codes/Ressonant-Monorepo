from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.auth.deps import CurrentUser
from app.modules.workspace_management.deps import get_workspace_management_service
from app.modules.workspace_management.schemas.dto import (
    GrantCreateRequest,
    GrantRevokeRequest,
    ManagementAccessResponse,
    ManagementGrantResponse,
)
from app.modules.workspace_management.usecases.services import WorkspaceManagementService

router = APIRouter(prefix="/workspaces/{workspace_id}/management", tags=["workspace-management"])
Service = Annotated[WorkspaceManagementService, Depends(get_workspace_management_service)]


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


@router.get("/access/me", response_model=ManagementAccessResponse)
def get_management_access(workspace_id: str, service: Service, current_user: CurrentUser) -> ManagementAccessResponse:
    return service.get_access_response(workspace_id, current_user)


@router.get("/grants", response_model=list[ManagementGrantResponse])
def list_management_grants(workspace_id: str, service: Service, current_user: CurrentUser) -> list[ManagementGrantResponse]:
    grants = service.list_grants(workspace_id, current_user)
    return [ManagementGrantResponse.model_validate(g) for g in grants]


@router.post("/grants", response_model=ManagementGrantResponse, status_code=201)
def upsert_management_grant(
    workspace_id: str,
    payload: GrantCreateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> ManagementGrantResponse:
    grant = service.create_or_update_grant(
        workspace_id,
        current_user,
        target_user_id=payload.user_id,
        level=payload.level,
        reason=payload.reason,
        request_id=_request_id(request),
    )
    return ManagementGrantResponse.model_validate(grant)


@router.delete("/grants/{target_user_id}", status_code=204)
def revoke_management_grant(
    workspace_id: str,
    target_user_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
    payload: GrantRevokeRequest | None = None,
) -> None:
    service.revoke_grant(
        workspace_id,
        current_user,
        target_user_id=target_user_id,
        reason=payload.reason if payload else None,
        request_id=_request_id(request),
    )
