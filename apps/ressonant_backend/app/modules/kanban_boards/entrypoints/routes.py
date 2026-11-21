from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.kanban_boards.deps import get_board_service
from app.modules.kanban_boards.schemas.dto import (
    BoardColumnCreate,
    BoardColumnList,
    BoardColumnReorderInput,
    BoardColumnResponse,
    BoardColumnUpdate,
    BoardCreate,
    BoardList,
    BoardResponse,
    BoardStatusUpdate,
    BoardUpdate,
)
from app.modules.kanban_boards.usecases.services import BoardService
from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/boards", tags=["boards"])

Service = Annotated[BoardService, Depends(get_board_service)]


@router.post("", response_model=BoardResponse, status_code=status.HTTP_201_CREATED)
def create_board(
    payload: BoardCreate,
    user: CurrentUser,
    service: Service,
) -> BoardResponse:
    """Cria um board. workspace_id e team_id vêm do payload; owner_id do JWT."""
    return BoardResponse.model_validate(service.create(payload, user.id))


@router.get("", response_model=BoardList)
def list_boards(
    user: CurrentUser,
    service: Service,
    workspace_id: str,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_ativo: bool | None = None,
) -> BoardList:
    """Lista boards de um workspace (só times que o usuário é membro)."""
    items, total = service.list_for_workspace(workspace_id, user.id, skip, limit, status_ativo)
    return BoardList(
        items=[BoardResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{board_id}", response_model=BoardResponse)
def get_board(
    board_id: str,
    user: CurrentUser,
    service: Service,
) -> BoardResponse:
    """Busca board por id (só se o usuário é membro do time)."""
    return BoardResponse.model_validate(service.get(board_id, user.id))


@router.put("/{board_id}", response_model=BoardResponse)
def update_board(
    board_id: str,
    payload: BoardUpdate,
    user: CurrentUser,
    service: Service,
) -> BoardResponse:
    """Atualiza board (só owner/admin do time)."""
    return BoardResponse.model_validate(service.update(board_id, payload, user.id))


@router.patch("/{board_id}/status", response_model=BoardResponse)
def set_board_status(
    board_id: str,
    payload: BoardStatusUpdate,
    user: CurrentUser,
    service: Service,
) -> BoardResponse:
    """Ativa ou desativa board (só admin do time)."""
    return BoardResponse.model_validate(service.set_status(board_id, payload.status_ativo, user.id))


@router.get("/{board_id}/columns", response_model=BoardColumnList)
def list_board_columns(
    board_id: str,
    user: CurrentUser,
    service: Service,
) -> BoardColumnList:
    """Lista colunas de um board (só se o usuário é membro do time)."""
    columns = service.list_columns(board_id, user.id)
    return BoardColumnList(
        items=[BoardColumnResponse.model_validate(c) for c in columns],
        total=len(columns),
    )


@router.post(
    "/{board_id}/columns",
    response_model=BoardColumnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_board_column(
    board_id: str,
    payload: BoardColumnCreate,
    user: CurrentUser,
    service: Service,
) -> BoardColumnResponse:
    """Cria uma coluna no board."""
    return BoardColumnResponse.model_validate(
        service.create_column(board_id, payload, user.id, user.interno_adm)
    )


@router.patch("/{board_id}/columns/reorder", response_model=BoardColumnList)
def reorder_board_columns(
    board_id: str,
    payload: BoardColumnReorderInput,
    user: CurrentUser,
    service: Service,
) -> BoardColumnList:
    """Reordena colunas do board (sequência completa)."""
    columns = service.reorder_columns(
        board_id, payload.ordered_column_ids, user.id, user.interno_adm
    )
    return BoardColumnList(
        items=[BoardColumnResponse.model_validate(c) for c in columns], total=len(columns)
    )


@router.patch("/{board_id}/columns/{column_id}", response_model=BoardColumnResponse)
def update_board_column(
    board_id: str,
    column_id: str,
    payload: BoardColumnUpdate,
    user: CurrentUser,
    service: Service,
) -> BoardColumnResponse:
    """Atualiza uma coluna do board."""
    return BoardColumnResponse.model_validate(
        service.update_column(board_id, column_id, payload, user.id, user.interno_adm)
    )


@router.delete("/{board_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board_column(
    board_id: str,
    column_id: str,
    user: CurrentUser,
    service: Service,
) -> None:
    """Exclui coluna (somente se não houver cards)."""
    service.delete_column(board_id, column_id, user.id, user.interno_adm)
