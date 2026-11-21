from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.teams.deps import get_team_service
from app.modules.teams.schemas.dto import (
    TeamCreate,
    TeamList,
    TeamMemberAdd,
    TeamMemberList,
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamResponse,
    TeamSoftDeleteInput,
    TeamStatusUpdate,
    TeamUpdate,
)
from app.modules.teams.usecases.services import TeamService
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/teams", tags=["teams"])

Service = Annotated[TeamService, Depends(get_team_service)]


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    user: CurrentUser,
    service: Service,
) -> TeamResponse:
    """Cria um team. workspace_id vem do payload; owner_id do JWT."""
    return TeamResponse.model_validate(service.create(payload, user.id))


@router.get("", response_model=TeamList)
def list_teams(
    user: CurrentUser,
    service: Service,
    workspace_id: str,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_ativo: bool | None = None,
) -> TeamList:
    """Lista teams de um workspace onde o usuário é membro do time."""
    items, total = service.list_for_workspace(workspace_id, user.id, skip, limit, status_ativo)
    return TeamList(
        items=[TeamResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/deleted", response_model=TeamList)
def list_deleted_teams(
    user: CurrentUser,
    service: Service,
    workspace_id: str,
) -> TeamList:
    """Lista equipes deletadas (soft delete) do workspace. Apenas owner/interno_adm."""
    items = service.list_deleted(workspace_id, user.id, user.interno_adm)
    return TeamList(
        items=[TeamResponse.model_validate(i) for i in items],
        total=len(items),
        skip=0,
        limit=len(items),
    )


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(
    team_id: str,
    user: CurrentUser,
    service: Service,
) -> TeamResponse:
    """Busca team por id (só se o usuário é membro)."""
    return TeamResponse.model_validate(service.get(team_id, user.id))


@router.put("/{team_id}", response_model=TeamResponse)
def update_team(
    team_id: str,
    payload: TeamUpdate,
    user: CurrentUser,
    service: Service,
) -> TeamResponse:
    """Atualiza team (só owner ou admin do team)."""
    return TeamResponse.model_validate(service.update(team_id, payload, user.id))


@router.patch("/{team_id}/status", response_model=TeamResponse)
def set_team_status(
    team_id: str,
    payload: TeamStatusUpdate,
    user: CurrentUser,
    service: Service,
) -> TeamResponse:
    """Ativa ou desativa team (só o owner)."""
    return TeamResponse.model_validate(service.set_status(team_id, payload.status_ativo, user.id))


@router.get(
    "/{team_id}/members",
    response_model=TeamMemberList,
)
def list_team_members(
    team_id: str,
    user: CurrentUser,
    service: Service,
) -> TeamMemberList:
    """Lista membros do team (só se o usuário é membro)."""
    members = service.list_members(team_id, user.id)
    return TeamMemberList(
        items=[TeamMemberResponse.model_validate(m) for m in members],
        total=len(members),
    )


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_team_member(
    team_id: str,
    payload: TeamMemberAdd,
    user: CurrentUser,
    service: Service,
) -> TeamMemberResponse:
    """Adiciona membro à equipe por e-mail exato ou user_id (owner/admin do workspace, admin do time ou interno_adm)."""  # noqa: E501 - text is part of the published OpenAPI description
    return TeamMemberResponse.model_validate(
        service.add_member(team_id, payload, user.id, user.interno_adm)
    )


@router.patch(
    "/{team_id}/members/{user_id}",
    response_model=TeamMemberResponse,
)
def update_team_member(
    team_id: str,
    user_id: str,
    payload: TeamMemberUpdate,
    user: CurrentUser,
    service: Service,
) -> TeamMemberResponse:
    """Altera papel do membro na equipe (owner/admin do workspace, admin do time ou interno_adm)."""
    return TeamMemberResponse.model_validate(
        service.update_member(team_id, user_id, payload, user.id, user.interno_adm)
    )


@router.post("/{team_id}/soft-delete", response_model=TeamResponse)
def soft_delete_team(
    team_id: str,
    payload: TeamSoftDeleteInput,
    user: CurrentUser,
    service: Service,
) -> TeamResponse:
    """Soft delete de equipe com reatribuição obrigatória de membros. Apenas owner/interno_adm."""
    return TeamResponse.model_validate(
        service.soft_delete(team_id, payload, user.id, user.interno_adm)
    )


@router.delete("/{team_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanent_delete_team(
    team_id: str,
    user: CurrentUser,
    service: Service,
) -> None:
    """Exclusão definitiva de equipe já deletada. Apenas owner/interno_adm."""
    service.permanent_delete(team_id, user.id, user.interno_adm)
