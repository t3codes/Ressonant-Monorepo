from __future__ import annotations

from app.common.exceptions import ConflictException
from app.common.security import hash_password
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from app.modules.user.schemas.dto import UserCreate, UserRegister, UserUpdate
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import ExceptionData, NotFoundException
from sqlalchemy.exc import IntegrityError


def _not_found() -> NotFoundException:
    return NotFoundException(
        ExceptionData(message="Usuário não encontrado", error_code="USER_NOT_FOUND"),
        is_expected=True,
    )


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _last_admin_protected() -> ConflictException:
    return _conflict(
        "Não é possível remover o último administrador da plataforma", "LAST_ADMIN_PROTECTED"
    )


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repo = repository

    def add_user(
        self,
        payload: UserRegister,
        *,
        status_ativo: bool = True,
        interno_adm: bool = False,
    ) -> User:
        """Prepara o usuário na Session; a transação fica com quem chama."""
        if self._repo.exists_by_email_or_cpf(payload.email, payload.cpf):
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS")
        user = User(
            email=payload.email,
            senha_hash=hash_password(payload.senha),
            cpf=payload.cpf,
            idade=payload.idade,
            termos_contrato=payload.termos_contrato,
            telefone=payload.telefone,
            status_ativo=status_ativo,
            interno_adm=interno_adm,
        )
        self._repo.add(user)
        return user

    def register(self, payload: UserRegister) -> User:
        """Cadastro público: sempre usuário comum e ativo."""
        try:
            user = self.add_user(payload)
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS") from None
        return user

    def create(self, payload: UserCreate) -> User:
        try:
            user = self.add_user(
                payload, status_ativo=payload.status_ativo, interno_adm=payload.interno_adm
            )
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS") from None
        return user

    def get(self, user_id: str) -> User:
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise _not_found()
        return user

    def list(self, skip: int, limit: int, status_ativo: bool | None) -> tuple[list[User], int]:
        return self._repo.list(skip, limit, status_ativo)

    def update(self, user_id: str, payload: UserUpdate) -> User:
        user = self.get(user_id)
        if payload.email != user.email and self._repo.get_by_email(payload.email):
            raise _conflict("E-mail já cadastrado", "EMAIL_ALREADY_EXISTS")
        user.email = payload.email
        user.telefone = payload.telefone
        user.idade = payload.idade
        if payload.termos_contrato is not None:
            user.termos_contrato = payload.termos_contrato
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail já cadastrado", "EMAIL_ALREADY_EXISTS") from None
        return user

    def _load_for_admin_change(self, user_id: str) -> tuple[User, list[str]]:
        """Trava os admins ativos antes de ler o alvo e decidir sobre a guarda."""
        admin_ids = self._repo.lock_active_admin_ids()
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise _not_found()
        self._repo.refresh(user)
        return user, admin_ids

    @staticmethod
    def _is_last_active_admin(user: User, admin_ids: list[str]) -> bool:
        return (
            user.id in admin_ids
            and len(admin_ids) == 1
            and bool(user.status_ativo)
            and bool(user.interno_adm)
        )

    def set_status(self, user_id: str, status_ativo: bool, actor_id: str | None = None) -> User:
        user, admin_ids = self._load_for_admin_change(user_id)
        before = {"status_ativo": bool(user.status_ativo), "interno_adm": bool(user.interno_adm)}
        if not status_ativo and self._is_last_active_admin(user, admin_ids):
            raise _last_admin_protected()
        user.status_ativo = status_ativo
        if before["interno_adm"]:
            self._record_admin_change(user, before, actor_id, "status")
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return user

    def set_admin(self, user_id: str, interno_adm: bool, actor_id: str | None = None) -> User:
        user, admin_ids = self._load_for_admin_change(user_id)
        before = {"status_ativo": bool(user.status_ativo), "interno_adm": bool(user.interno_adm)}
        if not interno_adm and self._is_last_active_admin(user, admin_ids):
            raise _last_admin_protected()
        user.interno_adm = interno_adm
        self._record_admin_change(user, before, actor_id, "admin")
        try:
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return user

    def _record_admin_change(
        self, user: User, before: dict[str, bool], actor_id: str | None, kind: str
    ) -> None:
        """Bump da versão do usuário + auditoria system no mesmo commit da mutação."""
        version = int(getattr(user, "permission_version", 1) or 1) + 1
        user.permission_version = version
        after = {
            "status_ativo": bool(user.status_ativo),
            "interno_adm": bool(user.interno_adm),
            "permission_version": version,
        }
        action = f"user.{kind}."
        if kind == "admin":
            action += "granted" if after["interno_adm"] else "revoked"
        else:
            action += "activated" if after["status_ativo"] else "deactivated"
        actor = self._repo.get_by_id(actor_id) if actor_id else None
        actor_version = (
            int(getattr(actor, "permission_version", 1) or 1) if actor is not None else None
        )
        self._repo.add_audit_event(
            AuditEvent(
                scope="system",
                actor_user_id=actor_id,
                actor_type="internal_admin" if actor_id else "system",
                actor_role="internal_admin",
                action=action,
                entity_type="user",
                entity_id=user.id,
                target_user_id=user.id,
                # ADR 0003 (v): a claim do evento é a versão do ator; a nova
                # versão do alvo fica registrada em `after`.
                permission_version=actor_version,
                before=before,
                after=after,
                result="success",
            )
        )
