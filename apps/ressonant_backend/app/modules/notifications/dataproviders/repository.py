from app.modules.notifications.domain.models import AppNotification
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self, user_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[AppNotification], int]:
        stmt = select(AppNotification).where(AppNotification.user_id == user_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(
            stmt.order_by(AppNotification.created_at.desc()).offset(skip).limit(limit)
        )
        return list(items), total

    def mark_read(self, ids: list[str], user_id: str) -> int:
        """Atualiza somente notificações do usuário; devolve quantas linhas mudaram."""
        if not ids:
            return 0
        result = self._db.execute(
            update(AppNotification)
            .where(
                AppNotification.id.in_(ids),
                AppNotification.user_id == user_id,
            )
            .values(read_at=func.now())
        )
        return result.rowcount or 0

    def mark_all_read(self, user_id: str, workspace_id: str) -> None:
        self._db.execute(
            __import__("sqlalchemy")
            .update(AppNotification)
            .where(AppNotification.user_id == user_id)
            .values(read_at=func.now())
        )

    def add(self, notification: AppNotification) -> AppNotification:
        self._db.add(notification)
        self._db.flush()
        return notification

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
