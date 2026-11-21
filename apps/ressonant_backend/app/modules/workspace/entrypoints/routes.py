from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.workspace.deps import get_workspace_service
from app.modules.workspace.schemas.dto import (
    WorkspaceCreate,
    WorkspaceList,
    WorkspaceMemberAdd,
    WorkspaceMemberList,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdate,
    WorkspaceResponse,
    WorkspaceStatusUpdate,
    WorkspaceUpdate,
)
from app.modules.workspace.usecases.services import WorkspaceService
from fastapi import APIRouter, Depends, Query, status

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


@router.get(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberList,
)
def list_workspace_members(
    workspace_id: str,
    user: CurrentUser,
    service: Service,
) -> WorkspaceMemberList:
    """Lista membros do workspace (só se o usuário é membro)."""
    members = service.list_members(workspace_id, user.id)
    return WorkspaceMemberList(
        items=[WorkspaceMemberResponse.model_validate(m) for m in members],
        total=len(members),
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
    """Adiciona membro ao workspace por e-mail exato ou user_id (owner/admin do workspace ou interno_adm)."""
    return WorkspaceMemberResponse.model_validate(
        service.add_member(workspace_id, payload, user.id, user.interno_adm)
    )


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberResponse,
)
def update_workspace_member(
    workspace_id: str,
    user_id: str,
    payload: WorkspaceMemberUpdate,
    user: CurrentUser,
    service: Service,
) -> WorkspaceMemberResponse:
    """Altera papel do membro (só owner do workspace ou interno_adm). role=owner transfere a propriedade."""
    return WorkspaceMemberResponse.model_validate(
        service.update_member(workspace_id, user_id, payload, user.id, user.interno_adm)
    )
