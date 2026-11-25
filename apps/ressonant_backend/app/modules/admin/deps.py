from typing import Annotated

from app.database.engine import get_db
from app.modules.admin.dataproviders.repository import AdminRepository
from app.modules.admin.usecases.services import AdminService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_admin_repository(db: Annotated[Session, Depends(get_db)]) -> AdminRepository:
    return AdminRepository(db)


def get_admin_service(
    repo: Annotated[AdminRepository, Depends(get_admin_repository)],
) -> AdminService:
    return AdminService(repo)
