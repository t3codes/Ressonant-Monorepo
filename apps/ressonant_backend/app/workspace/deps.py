from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.workspace.repository import WorkspaceRepository
from app.workspace.services import WorkspaceService


def get_workspace_repository(db: Annotated[Session, Depends(get_db)]) -> WorkspaceRepository:
    return WorkspaceRepository(db)


def get_workspace_service(
    repo: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceService:
    return WorkspaceService(repo)
