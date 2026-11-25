from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.workspace_management.deps import get_workspace_management_service
from app.modules.workspace_management.schemas.dto import (
    AdminTeamResponse,
    AuditEventResponse,
    BlockedCardResponse,
    CapabilityBatchRequest,
    GrantCreateRequest,
    GrantRevokeRequest,
    ManagementAccessResponse,
    ManagementGrantResponse,
    TargetAccessResponse,
    WorkspacePersonDetailResponse,
    WorkspacePersonResponse,
    WorkspacePersonTeamChangeRequest,
)
from app.modules.workspace_management.usecases.services import WorkspaceManagementService
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/workspaces/{workspace_id}/management", tags=["workspace-management"])
Service = Annotated[WorkspaceManagementService, Depends(get_workspace_management_service)]


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


@router.get("/access/me", response_model=ManagementAccessResponse)
def get_management_access(
    workspace_id: str, service: Service, current_user: CurrentUser
) -> ManagementAccessResponse:
    return service.get_access_response(workspace_id, current_user)


@router.get("/access/{target_user_id}", response_model=TargetAccessResponse)
def get_target_management_access(
    workspace_id: str,
    target_user_id: str,
    service: Service,
    current_user: CurrentUser,
) -> TargetAccessResponse:
    return service.get_target_access(workspace_id, current_user, target_user_id)


@router.put("/access/{target_user_id}", response_model=TargetAccessResponse)
def update_target_management_access(
    workspace_id: str,
    target_user_id: str,
    payload: CapabilityBatchRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> TargetAccessResponse:
    return service.update_capabilities(
        workspace_id,
        current_user,
        target_user_id,
        items=payload.items,
        reason=payload.reason,
        request_id=_request_id(request),
    )


@router.get("/grants", response_model=list[ManagementGrantResponse])
def list_management_grants(
    workspace_id: str, service: Service, current_user: CurrentUser
) -> list[ManagementGrantResponse]:
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


@router.get("/people", response_model=list[WorkspacePersonResponse])
def list_management_people(
    workspace_id: str, service: Service, current_user: CurrentUser
) -> list[WorkspacePersonResponse]:
    return [
        WorkspacePersonResponse.model_validate(x)
        for x in service.list_people(workspace_id, current_user)
    ]


@router.get("/people/{target_user_id}", response_model=WorkspacePersonDetailResponse)
def get_management_person(
    workspace_id: str,
    target_user_id: str,
    service: Service,
    current_user: CurrentUser,
) -> WorkspacePersonDetailResponse:
    return WorkspacePersonDetailResponse.model_validate(
        service.get_person(workspace_id, current_user, target_user_id)
    )


@router.delete("/people/{target_user_id}", status_code=204)
def remove_management_person(
    workspace_id: str,
    target_user_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> None:
    service.remove_person(
        workspace_id,
        current_user,
        target_user_id,
        request_id=_request_id(request),
    )


@router.patch("/people/{target_user_id}/team", response_model=WorkspacePersonDetailResponse)
def change_management_person_team(
    workspace_id: str,
    target_user_id: str,
    payload: WorkspacePersonTeamChangeRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> WorkspacePersonDetailResponse:
    return WorkspacePersonDetailResponse.model_validate(
        service.change_person_team(
            workspace_id,
            current_user,
            target_user_id,
            target_team_id=payload.target_team_id,
            from_team_id=payload.from_team_id,
            request_id=_request_id(request),
        )
    )


@router.get("/teams", response_model=list[AdminTeamResponse])
def list_management_teams(
    workspace_id: str, service: Service, current_user: CurrentUser, include_deleted: bool = False
) -> list[AdminTeamResponse]:
    return [
        AdminTeamResponse.model_validate(x)
        for x in service.list_teams(workspace_id, current_user, include_deleted=include_deleted)
    ]


@router.get("/blocked-cards", response_model=list[BlockedCardResponse])
def list_management_blocked_cards(
    workspace_id: str, service: Service, current_user: CurrentUser
) -> list[BlockedCardResponse]:
    return [
        BlockedCardResponse.model_validate(x)
        for x in service.list_blocked_cards(workspace_id, current_user)
    ]


@router.get("/audit-events", response_model=list[AuditEventResponse])
def list_management_audit_events(
    workspace_id: str, service: Service, current_user: CurrentUser, skip: int = 0, limit: int = 50
) -> list[AuditEventResponse]:
    return [
        AuditEventResponse.model_validate(x)
        for x in service.list_audit(workspace_id, current_user, skip=skip, limit=limit)
    ]
