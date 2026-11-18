from typing import Annotated

from app.database.engine import get_db
from app.modules.reactions.dataproviders.repository import ReactionRepository
from app.modules.reactions.usecases.services import ReactionService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_reaction_repository(db: Annotated[Session, Depends(get_db)]) -> ReactionRepository:
    return ReactionRepository(db)


def get_reaction_service(
    repo: Annotated[ReactionRepository, Depends(get_reaction_repository)],
) -> ReactionService:
    return ReactionService(repo)
