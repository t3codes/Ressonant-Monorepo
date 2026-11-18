from typing import Annotated

from app.database.engine import get_db
from app.modules.notifications.dataproviders.repository import NotificationRepository
from app.modules.notifications.usecases.services import NotificationService
from fastapi import Depends
from sqlalchemy.orm import Session


def get_notification_repository(db: Annotated[Session, Depends(get_db)]) -> NotificationRepository:
    return NotificationRepository(db)


def get_notification_service(
    repo: Annotated[NotificationRepository, Depends(get_notification_repository)],
) -> NotificationService:
    return NotificationService(repo)
