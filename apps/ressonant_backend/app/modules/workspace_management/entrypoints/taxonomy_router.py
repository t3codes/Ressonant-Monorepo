from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.workspace_management.deps import get_workspace_management_service
from app.modules.workspace_management.schemas.dto import (
    TaxonomyCreateRequest,
    TaxonomyDeactivateRequest,
    TaxonomyGrantCreateRequest,
    TaxonomyGrantResponse,
    TaxonomyGrantRevokeRequest,
    TaxonomyKind,
    TaxonomyPatchRequest,
    TaxonomyResponse,
)
from app.modules.workspace_management.usecases.services import WorkspaceManagementService
from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/workspaces/{workspace_id}/management", tags=["workspace-taxonomy"])
Service = Annotated[WorkspaceManagementService, Depends(get_workspace_management_service)]


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


def _break_glass_reason(request: Request) -> str | None:
    return request.headers.get("x-break-glass-reason")


@router.get("/taxonomy", response_model=list[TaxonomyResponse])
def list_taxonomy(
    workspace_id: str,
    kind: TaxonomyKind,
    service: Service,
    current_user: CurrentUser,
    include_inactive: bool = False,
) -> list[TaxonomyResponse]:
    items = service.list_taxonomy(
        workspace_id, current_user, kind=kind, include_inactive=include_inactive
    )
    return [TaxonomyResponse.model_validate(item) for item in items]


@router.post("/taxonomy", response_model=TaxonomyResponse, status_code=201)
def create_taxonomy(
    workspace_id: str,
    payload: TaxonomyCreateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> TaxonomyResponse:
    item = service.create_taxonomy(
        workspace_id,
        current_user,
        kind=payload.kind,
        name=payload.name,
        color=payload.color,
        request_id=_request_id(request),
        break_glass_reason=_break_glass_reason(request),
    )
    return TaxonomyResponse.model_validate(item)


@router.patch("/taxonomy/{taxonomy_id}", response_model=TaxonomyResponse)
def patch_taxonomy(
    workspace_id: str,
    taxonomy_id: str,
    payload: TaxonomyPatchRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> TaxonomyResponse:
    item = service.patch_taxonomy_color(
        workspace_id,
        current_user,
        taxonomy_id,
        color=payload.color,
        request_id=_request_id(request),
        break_glass_reason=_break_glass_reason(request),
    )
    return TaxonomyResponse.model_validate(item)


@router.post("/taxonomy/{taxonomy_id}/deactivate", response_model=TaxonomyResponse)
def deactivate_taxonomy(
    workspace_id: str,
    taxonomy_id: str,
    payload: TaxonomyDeactivateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> TaxonomyResponse:
    item = service.deactivate_taxonomy(
        workspace_id,
        current_user,
        taxonomy_id,
        reason=payload.reason,
        request_id=_request_id(request),
        break_glass_reason=_break_glass_reason(request),
    )
    return TaxonomyResponse.model_validate(item)


@router.get("/taxonomy-grants", response_model=list[TaxonomyGrantResponse])
def list_taxonomy_grants(
    workspace_id: str, service: Service, current_user: CurrentUser
) -> list[TaxonomyGrantResponse]:
    grants = service.list_taxonomy_grants(workspace_id, current_user)
    return [TaxonomyGrantResponse.model_validate(grant) for grant in grants]


@router.post("/taxonomy-grants", response_model=TaxonomyGrantResponse, status_code=201)
def create_taxonomy_grant(
    workspace_id: str,
    payload: TaxonomyGrantCreateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> TaxonomyGrantResponse:
    grant = service.grant_taxonomy(
        workspace_id,
        current_user,
        target_user_id=payload.user_id,
        reason=payload.reason,
        request_id=_request_id(request),
    )
    return TaxonomyGrantResponse.model_validate(grant)


@router.delete("/taxonomy-grants/{target_user_id}", status_code=204)
def revoke_taxonomy_grant(
    workspace_id: str,
    target_user_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
    payload: TaxonomyGrantRevokeRequest | None = None,
) -> None:
    service.revoke_taxonomy_grant(
        workspace_id,
        current_user,
        target_user_id=target_user_id,
        reason=payload.reason if payload else None,
        request_id=_request_id(request),
    )
