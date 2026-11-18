import uuid

from app.modules.user.domain.models import User
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, user_id: str) -> User | None:
        try:
            uuid.UUID(user_id)
        except ValueError:
            return None
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._db.scalar(select(User).where(User.email == email))

    def exists_by_email_or_cpf(self, email: str, cpf: str) -> bool:
        stmt = select(User.id).where((User.email == email) | (User.cpf == cpf)).limit(1)
        return self._db.scalar(stmt) is not None

    def list(self, skip: int, limit: int, status_ativo: bool | None) -> tuple[list[User], int]:
        stmt = select(User)
        if status_ativo is not None:
            stmt = stmt.where(User.status_ativo == status_ativo)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(stmt.order_by(User.criado_em, User.id).offset(skip).limit(limit))
        return list(items), total

    def add(self, user: User) -> User:
        self._db.add(user)
        self._db.flush()
        return user

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
