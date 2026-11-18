from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.reactions.deps import get_reaction_service
from app.modules.reactions.schemas.dto import ReactionList, ReactionToggle
from app.modules.reactions.usecases.services import ReactionService
from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/messages/{message_id}/reactions", tags=["reactions"])

Service = Annotated[ReactionService, Depends(get_reaction_service)]


@router.post("", response_model=dict, status_code=status.HTTP_200_OK)
def toggle_reaction(
    message_id: str,
    payload: ReactionToggle,
    user: CurrentUser,
    service: Service,
) -> dict:
    return service.toggle(payload)


@router.get("", response_model=ReactionList)
def list_reactions(
    message_id: str,
    service: Service,
) -> ReactionList:
    return service.list_by_message_ids([message_id])
