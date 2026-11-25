from typing import Annotated

from app.database.engine import get_db
from app.modules.auth.deps import CurrentUser
from app.modules.notifications.deps import get_notification_service
from app.modules.notifications.schemas.dto import (
    NotificationList,
    NotificationPublicCreate,
    NotificationResponse,
)
from app.modules.notifications.usecases.create_notification_usecase import (
    create_notification_for_user,
)
from app.modules.notifications.usecases.services import NotificationService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/notifications", tags=["notifications"])

Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("", response_model=NotificationList)
def list_notifications(
    user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationList:
    return service.list_for_user(user.id, skip, limit)


@router.patch("/mark-read", status_code=204)
def mark_read(
    ids: list[str],
    user: CurrentUser,
    service: Service,
) -> None:
    service.mark_read(ids, user.id)
    return None


@router.patch("/mark-all-read", status_code=204)
def mark_all_read(
    user: CurrentUser,
    service: Service,
) -> None:
    service.mark_all_read(user.id, "")
    return None


@router.post("", response_model=NotificationResponse, status_code=201)
def create_notification(
    payload: NotificationPublicCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> NotificationResponse:
    return NotificationResponse.model_validate(create_notification_for_user(db, payload, user.id))
