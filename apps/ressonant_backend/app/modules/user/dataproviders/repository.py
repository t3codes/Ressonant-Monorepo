from __future__ import annotations

import uuid

from app.modules.user.domain.models import User
from app.modules.workspace_management.domain.models import AuditEvent
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

    def count(self) -> int:
        return self._db.scalar(select(func.count()).select_from(User)) or 0

    def lock_active_admin_ids(self) -> list[str]:
        """Trava todos os admins ativos em ordem determinística (CYB-003).

        Uma única varredura `ORDER BY id ... FOR UPDATE` evita o deadlock de
        duas revogações concorrentes que travariam alvos em ordens opostas. O
        alvo, quando é admin ativo, está nessa lista; a contagem feita pelo
        service acontece depois do lock e antes de qualquer mutação.
        """
        stmt = (
            select(User.id)
            .where(User.interno_adm.is_(True), User.status_ativo.is_(True))
            .order_by(User.id.asc())
            .with_for_update()
        )
        return list(self._db.scalars(stmt))

    def refresh(self, user: User) -> None:
        """Recarrega a linha já travada, evitando valor obsoleto no identity map."""
        self._db.refresh(user)

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
