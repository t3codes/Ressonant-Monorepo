from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.readstates.deps import get_read_state_service
from app.modules.readstates.schemas.dto import ReadStateList, ReadStateResponse
from app.modules.readstates.usecases.services import ReadStateService
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/read-states", tags=["read-states"])

Service = Annotated[ReadStateService, Depends(get_read_state_service)]


@router.get("", response_model=ReadStateList)
def list_read_states(
    user: CurrentUser,
    service: Service,
) -> ReadStateList:
    return service.list_for_user(user.id)


@router.post("/{room_id}", response_model=ReadStateResponse)
def mark_read(
    room_id: str,
    user: CurrentUser,
    service: Service,
) -> ReadStateResponse:
    return service.mark_read(user.id, room_id)
