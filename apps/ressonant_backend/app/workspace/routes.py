from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.deps import CurrentUser
from app.workspace.deps import get_workspace_service
from app.workspace.schemas import (
    WorkspaceCreate,
    WorkspaceList,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceStatusUpdate,
    WorkspaceUpdate,
)
from app.workspace.services import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

Service = Annotated[WorkspaceService, Depends(get_workspace_service)]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    user: CurrentUser,
    service: Service,
) -> WorkspaceResponse:
    """Cria um workspace. O owner é o usuário autenticado (extraído do JWT)."""
    return WorkspaceResponse.model_validate(service.create(payload, user.id))


@router.get("", response_model=WorkspaceList)
def list_workspaces(
    user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_ativo: bool | None = None,
) -> WorkspaceList:
    """Lista workspaces do usuário autenticado (dono ou membro)."""
    items, total = service.list_for_user(user.id, skip, limit, status_ativo)
    return WorkspaceList(
        items=[WorkspaceResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    user: CurrentUser,
    service: Service,
) -> WorkspaceResponse:
    """Busca workspace por id (só se o usuário é membro)."""
    return WorkspaceResponse.model_validate(service.get(workspace_id, user.id))


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    user: CurrentUser,
    service: Service,
) -> WorkspaceResponse:
    """Atualiza workspace (só owner ou admin do workspace)."""
    return WorkspaceResponse.model_validate(service.update(workspace_id, payload, user.id))


@router.patch("/{workspace_id}/status", response_model=WorkspaceResponse)
def set_workspace_status(
    workspace_id: str,
    payload: WorkspaceStatusUpdate,
    user: CurrentUser,
    service: Service,
) -> WorkspaceResponse:
    """Ativa ou desativa workspace (só o owner)."""
    return WorkspaceResponse.model_validate(
        service.set_status(workspace_id, payload.status_ativo, user.id)
    )


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_member(
    workspace_id: str,
    payload: WorkspaceMemberAdd,
    user: CurrentUser,
    service: Service,
) -> WorkspaceMemberResponse:
    """Adiciona membro ao workspace (só owner ou admin do workspace)."""
    return WorkspaceMemberResponse.model_validate(
        service.add_member(workspace_id, payload, user.id)
    )
