import uuid

from app.modules.mail.domain.models import Email
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class MailRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, email_id: str) -> Email | None:
        try:
            uuid.UUID(email_id)
        except ValueError:
            return None
        return self._db.get(Email, email_id)

    def list_for_user(
        self, user_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Email], int]:
        stmt = select(Email).where(Email.sender_id == user_id)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(stmt.order_by(Email.criado_em, Email.id).offset(skip).limit(limit))
        return list(items), total

    def add(self, email: Email) -> Email:
        self._db.add(email)
        self._db.flush()
        return email

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
