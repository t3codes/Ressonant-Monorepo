from typing import Annotated

from app.database.engine import get_db
from app.modules.readstates.dataproviders.repository import ReadStateRepository
from app.modules.readstates.usecases.services import ReadStateService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_read_state_repository(db: Annotated[Session, Depends(get_db)]) -> ReadStateRepository:
    return ReadStateRepository(db)


def get_read_state_service(
    repo: Annotated[ReadStateRepository, Depends(get_read_state_repository)],
) -> ReadStateService:
    return ReadStateService(repo)
