from app.modules.notifications.dataproviders.repository import NotificationRepository
from app.modules.notifications.domain.models import AppNotification
from app.modules.notifications.schemas.dto import (
    NotificationCreate,
    NotificationList,
    NotificationResponse,
)


class NotificationService:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    def list_for_user(self, user_id: str, skip: int = 0, limit: int = 50) -> NotificationList:
        items, total = self._repo.list_for_user(user_id, skip, limit)
        return NotificationList(
            items=[NotificationResponse.model_validate(i) for i in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def mark_read(self, ids: list[str]) -> None:
        self._repo.mark_read(ids)
        self._repo.commit()

    def mark_all_read(self, user_id: str, workspace_id: str) -> None:
        self._repo.mark_all_read(user_id, workspace_id)
        self._repo.commit()

    def create(self, payload: NotificationCreate) -> AppNotification:
        notification = AppNotification(
            user_id=payload.user_id,
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
        )
        try:
            self._repo.add(notification)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return notification
