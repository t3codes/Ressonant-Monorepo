from typing import Annotated

from app.config.settings import Settings, get_settings
from app.database.engine import get_db
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.usecases.services import InvitationService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_organization_repository(db: Annotated[Session, Depends(get_db)]) -> OrganizationRepository:
    return OrganizationRepository(db)


def get_invitation_service(
    repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvitationService:
    return InvitationService(repo, settings=settings)
