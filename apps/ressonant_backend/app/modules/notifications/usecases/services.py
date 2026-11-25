from app.modules.notifications.dataproviders.repository import NotificationRepository
from app.modules.notifications.domain.models import AppNotification
from app.modules.notifications.schemas.dto import (
    NotificationCreate,
    NotificationList,
    NotificationResponse,
)
from common.errors import BadRequestException, ExceptionData


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

    def mark_read(self, ids: list[str], user_id: str) -> None:
        updated = self._repo.mark_read(ids, user_id)
        if updated != len(set(ids)):
            self._repo.rollback()
            # 400 (e não 404) preserva o contrato publicado e não distingue
            # "inexistente" de "pertence a outro usuário".
            raise BadRequestException(
                ExceptionData(
                    message="Notificação não encontrada para este usuário",
                    error_code="NOTIFICATION_NOT_FOUND",
                ),
                is_expected=True,
            )
        self._repo.commit()

    def mark_all_read(self, user_id: str, workspace_id: str) -> None:
        self._repo.mark_all_read(user_id, workspace_id)
        self._repo.commit()

    def create(self, payload: NotificationCreate) -> AppNotification:
        return self.create_many([payload])[0]

    def create_many(self, payloads: list[NotificationCreate]) -> list[AppNotification]:
        """Grava várias notificações em uma transação (um destino por chamada ao bus)."""
        if not payloads:
            return []
        notifications = [
            AppNotification(
                user_id=payload.user_id,
                kind=payload.kind,
                title=payload.title,
                body=payload.body,
                workspace_id=payload.workspace_id,
                actor_id=payload.actor_id,
                message_id=payload.message_id,
                room_id=payload.room_id,
                room_kind=payload.room_kind,
            )
            for payload in payloads
        ]
        try:
            for notification in notifications:
                self._repo.add(notification)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return notifications
