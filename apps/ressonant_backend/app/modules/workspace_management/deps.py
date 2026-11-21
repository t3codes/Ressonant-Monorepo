from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.modules.workspace_management.dataproviders.repository import WorkspaceManagementRepository
from app.modules.workspace_management.usecases.services import WorkspaceManagementService


def get_workspace_management_repository(
    db: Annotated[Session, Depends(get_db)],
) -> WorkspaceManagementRepository:
    return WorkspaceManagementRepository(db)


def get_workspace_management_service(
    repo: Annotated[WorkspaceManagementRepository, Depends(get_workspace_management_repository)],
) -> WorkspaceManagementService:
    return WorkspaceManagementService(repo)
