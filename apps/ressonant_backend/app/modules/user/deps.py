from typing import Annotated

from app.database.engine import get_db
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.usecases.services import UserService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_user_repository(db: Annotated[Session, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserService:
    return UserService(repo)
