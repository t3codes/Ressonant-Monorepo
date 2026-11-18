from typing import Annotated

from app.database.engine import get_db
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.usecases.services import TeamService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_team_repository(db: Annotated[Session, Depends(get_db)]) -> TeamRepository:
    return TeamRepository(db)


def get_team_service(
    repo: Annotated[TeamRepository, Depends(get_team_repository)],
) -> TeamService:
    return TeamService(repo)
