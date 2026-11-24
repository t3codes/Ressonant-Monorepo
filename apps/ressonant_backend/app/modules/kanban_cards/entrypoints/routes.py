from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.kanban_cards.deps import get_card_service
from app.modules.kanban_cards.schemas.dto import (
    CardBlockInput,
    CardCommentCreate,
    CardCommentList,
    CardCommentResponse,
    CardCreate,
    CardDeleteInput,
    CardList,
    CardMoveInput,
    CardResponse,
    CardUnblockInput,
    CardUpdate,
)
from app.modules.kanban_cards.usecases.services import CardService
from fastapi import APIRouter, Body, Depends, Query, Response, status

router = APIRouter(prefix="/cards", tags=["cards"])

Service = Annotated[CardService, Depends(get_card_service)]


@router.post("", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
def create_card(
    payload: CardCreate,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Cria um card. columnId é ignorado: nasce no backlog do time."""
    return CardResponse.model_validate(service.create(payload, user.id))


@router.get("", response_model=CardList)
def list_cards(
    user: CurrentUser,
    service: Service,
    board_id: str,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_ativo: bool | None = None,
) -> CardList:
    """Lista cards de um board (só se o usuário é membro do time)."""
    items, total = service.list_for_board(board_id, user.id, skip, limit, status_ativo)
    return CardList(
        items=[CardResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{card_id}", response_model=CardResponse)
def get_card(
    card_id: str,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Busca card por id (só se o usuário é membro do time)."""
    return CardResponse.model_validate(service.get(card_id, user.id))


@router.put("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: str,
    payload: CardUpdate,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Atualiza card com otimistic locking (expectedVersion)."""
    return CardResponse.model_validate(service.update(card_id, payload, user.id))


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: str,
    user: CurrentUser,
    service: Service,
    payload: Annotated[CardDeleteInput | None, Body()] = None,
) -> Response:
    """Exclui card (204) com auditoria append-only na mesma transação."""
    service.delete(card_id, payload, user.id, user.interno_adm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{card_id}/move", response_model=CardResponse)
def move_card(
    card_id: str,
    input_data: CardMoveInput,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Move card entre colunas com otimistic locking."""
    return CardResponse.model_validate(service.move(card_id, input_data, user.id, user.interno_adm))


@router.post("/{card_id}/block", response_model=CardResponse)
def block_card(
    card_id: str,
    payload: CardBlockInput,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Bloqueia card (não pode ser movido até desbloqueio)."""
    return CardResponse.model_validate(service.block(card_id, payload, user.id, user.interno_adm))


@router.post("/{card_id}/unblock", response_model=CardResponse)
def unblock_card(
    card_id: str,
    payload: CardUnblockInput,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Desbloqueia card. Quem bloqueou ou owner/interno_adm (com justificativa auditada)."""
    return CardResponse.model_validate(service.unblock(card_id, payload, user.id, user.interno_adm))


@router.post(
    "/{card_id}/clone",
    response_model=CardResponse,
    status_code=status.HTTP_201_CREATED,
)
def clone_card(
    card_id: str,
    user: CurrentUser,
    service: Service,
) -> CardResponse:
    """Clona card no backlog do time (sem comentários/histórico)."""
    return CardResponse.model_validate(service.clone(card_id, user.id))


@router.post("/{card_id}/comments", response_model=CardCommentResponse, status_code=201)
def create_card_comment(
    card_id: str,
    payload: CardCommentCreate,
    user: CurrentUser,
    service: Service,
) -> CardCommentResponse:
    """Cria comentário; author_id é sempre o usuário autenticado."""
    return CardCommentResponse.model_validate(service.create_comment(card_id, payload, user.id))


@router.get("/{card_id}/comments", response_model=CardCommentList)
def list_card_comments(
    card_id: str,
    user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CardCommentList:
    """Lista comentários do card (persistência verificável após reload)."""
    items, total = service.list_comments(card_id, user.id, skip, limit)
    return CardCommentList(
        items=[CardCommentResponse.model_validate(item) for item in items],
        total=total,
    )
