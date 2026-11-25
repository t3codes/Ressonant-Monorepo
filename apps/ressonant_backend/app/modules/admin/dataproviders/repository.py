import uuid

from app.modules.admin.domain.models import SystemSetting
from app.modules.billing.domain.models import Plan
from app.modules.user.domain.models import User
from app.modules.workspace_management.domain.models import AuditEvent
from sqlalchemy import select
from sqlalchemy.orm import Session


class AdminRepository:
    """Única camada do backoffice que fala com a Session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
        except (TypeError, ValueError):
            return False
        return True

    def list_superusers(self) -> list[User]:
        return list(
            self._db.scalars(
                select(User)
                .where(User.interno_adm.is_(True))
                .order_by(User.email.asc(), User.id.asc())
            )
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self._db.scalar(select(User).where(User.email == email.lower()))

    def get_user_by_id(self, user_id: str) -> User | None:
        if not self._is_uuid(user_id):
            return None
        return self._db.get(User, user_id)

    def add_user(self, user: User) -> User:
        self._db.add(user)
        self._db.flush()
        return user

    def list_plans(self) -> list[Plan]:
        return list(self._db.scalars(select(Plan).order_by(Plan.code.asc(), Plan.id.asc())))

    def get_plan(self, plan_id: str) -> Plan | None:
        if not self._is_uuid(plan_id):
            return None
        return self._db.get(Plan, plan_id)

    def get_plan_by_code(self, code: str) -> Plan | None:
        return self._db.scalar(select(Plan).where(Plan.code == code))

    def add_plan(self, plan: Plan) -> Plan:
        self._db.add(plan)
        self._db.flush()
        return plan

    def list_settings(self) -> list[SystemSetting]:
        return list(self._db.scalars(select(SystemSetting).order_by(SystemSetting.key.asc())))

    def get_setting(self, key: str) -> SystemSetting | None:
        return self._db.get(SystemSetting, key)

    def add_system_setting(self, setting: SystemSetting) -> SystemSetting:
        self._db.add(setting)
        self._db.flush()
        return setting

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
