from typing import Annotated

from app.database.engine import get_db
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from app.modules.workspace.usecases.services import WorkspaceService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_workspace_repository(db: Annotated[Session, Depends(get_db)]) -> WorkspaceRepository:
    return WorkspaceRepository(db)


def get_workspace_service(
    repo: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceService:
    return WorkspaceService(repo)
