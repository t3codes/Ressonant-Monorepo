from typing import Annotated

from app.database.engine import get_db
from app.modules.context.dataproviders.repository import ContextRepository
from app.modules.context.usecases.services import ContextService
from app.modules.workspace_management.deps import get_workspace_management_service
from app.modules.workspace_management.usecases.services import WorkspaceManagementService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_context_repository(db: Annotated[Session, Depends(get_db)]) -> ContextRepository:
    return ContextRepository(db)


def get_context_service(
    repo: Annotated[ContextRepository, Depends(get_context_repository)],
    management: Annotated[WorkspaceManagementService, Depends(get_workspace_management_service)],
) -> ContextService:
    return ContextService(repo, management)
