from typing import Annotated

from app.modules.auth.deps import CurrentUser
from app.modules.context.deps import get_context_service
from app.modules.context.schemas.dto import MeContextResponse
from app.modules.context.usecases.services import ContextService
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/me", tags=["context"])


@router.get("/context", response_model=MeContextResponse)
def get_context(
    service: Annotated[ContextService, Depends(get_context_service)],
    user: CurrentUser,
) -> MeContextResponse:
    """Bootstrap do cliente em uma chamada, sem montar contexto no frontend."""
    return service.get_context(user)
