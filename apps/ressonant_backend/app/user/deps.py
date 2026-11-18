from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.user.repository import UserRepository
from app.user.services import UserService


def get_user_service(db: Annotated[Session, Depends(get_db)]) -> UserService:
    return UserService(UserRepository(db))
