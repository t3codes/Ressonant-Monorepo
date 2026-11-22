from typing import Annotated

from app.database.engine import get_db
from app.modules.organization.dataproviders.repository import OrganizationRepository
from fastapi import Depends
from sqlalchemy.orm import Session


def get_organization_repository(db: Annotated[Session, Depends(get_db)]) -> OrganizationRepository:
    return OrganizationRepository(db)
