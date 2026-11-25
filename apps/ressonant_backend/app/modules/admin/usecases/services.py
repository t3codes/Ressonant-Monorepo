import re

from app.common.exceptions import ConflictException
from app.common.security import hash_password
from app.modules.admin.dataproviders.repository import AdminRepository
from app.modules.admin.domain.models import SystemSetting
from app.modules.admin.schemas.dto import (
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    SuperuserCreate,
    SuperuserSummary,
    SystemSettingResponse,
    SystemSettingUpdate,
    mask_cpf,
)
from app.modules.billing.domain.models import Plan
from app.modules.user.domain.models import User
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import BadRequestException, ExceptionData, NotFoundException
from sqlalchemy.exc import IntegrityError

_SECRET_KEY_RE = re.compile(
    r"(?i)(token|senha|password|passwd|secret|api[\s_-]?key|credential|private|chave|segredo)"
)
_PII_KEY_RE = re.compile(
    r"(?i)(token|senha|password|passwd|secret|api[\s_-]?key|credential|private|chave|segredo|"
    r"email|e-mail|cpf|telefone|phone|nome|name)"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CPF_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
# CYB-004 (hardening): chave inocente não pode abrigar token opaco em claro.
_OPAQUE_SECRET_RE = re.compile(
    r"(?i)\b(?:sk|rk|pk|gh[pousr]|xox[abprs]|AKIA)[-_][A-Za-z0-9_-]{12,}\b"
)


def _bad_request(message: str, code: str) -> BadRequestException:
    return BadRequestException(ExceptionData(message=message, error_code=code), is_expected=True)


def _conflict(message: str, code: str) -> ConflictException:
    return ConflictException(ExceptionData(message=message, error_code=code), is_expected=True)


def _not_found(message: str, code: str) -> NotFoundException:
    return NotFoundException(ExceptionData(message=message, error_code=code), is_expected=True)


def _redact(value: object) -> object:
    """Remove PII e segredos de antes/depois do AuditEvent de configuração."""
    if isinstance(value, dict):
        return {
            key: "***" if _PII_KEY_RE.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        redacted = _EMAIL_RE.sub("***", value)
        return _CPF_RE.sub("***", redacted)
    return value


def _contains_sensitive(value: object) -> bool:
    """Barra segredos/PII antes de persistirem em system_settings."""
    if isinstance(value, dict):
        return any(
            _PII_KEY_RE.search(str(key)) is not None or _contains_sensitive(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return any(_contains_sensitive(item) for item in value)
    if isinstance(value, str):
        return (
            _EMAIL_RE.search(value) is not None
            or _CPF_RE.search(value) is not None
            or _OPAQUE_SECRET_RE.search(value) is not None
        )
    return False


def _summary(user: User) -> SuperuserSummary:
    return SuperuserSummary(
        id=user.id,
        nome=user.name,
        email=user.email,
        cpf_masked=mask_cpf(user.cpf),
        telefone=user.telefone,
        status_ativo=bool(user.status_ativo),
        interno_adm=bool(user.interno_adm),
        permission_version=int(getattr(user, "permission_version", 1) or 1),
        criado_em=user.criado_em,
    )


class AdminService:
    def __init__(self, repository: AdminRepository) -> None:
        self._repo = repository

    # ---- superusers -----------------------------------------------------

    def list_superusers(self) -> list[SuperuserSummary]:
        return [_summary(user) for user in self._repo.list_superusers()]

    def create_superuser(self, payload: SuperuserCreate, actor_id: str) -> SuperuserSummary:
        user = self._repo.get_user_by_email(payload.email)
        if user is None:
            if not payload.password:
                raise _bad_request(
                    "Senha obrigatória para criar um novo superuser", "PASSWORD_REQUIRED"
                )
            user = User(
                email=payload.email,
                senha_hash=hash_password(payload.password),
                cpf=payload.cpf,
                telefone=payload.telefone,
                idade=None,
                termos_contrato=False,
                status_ativo=True,
                interno_adm=True,
                name=payload.nome,
            )
            self._repo.add_user(user)
            action = "admin.superuser.created"
            before = None
        else:
            if user.cpf != payload.cpf:
                raise _conflict("CPF divergente do usuário existente", "CPF_MISMATCH")
            before = {
                "interno_adm": bool(user.interno_adm),
                "status_ativo": bool(user.status_ativo),
            }
            user.interno_adm = True
            user.status_ativo = True
            user.name = payload.nome
            action = "admin.superuser.promoted"

        user.permission_version = int(getattr(user, "permission_version", 1) or 1) + 1
        after = {
            "interno_adm": True,
            "status_ativo": True,
            "permission_version": user.permission_version,
        }
        self._audit(
            action=action,
            actor_id=actor_id,
            entity_type="user",
            target_id=user.id,
            target_user_id=user.id,
            before=before,
            after=after,
        )
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("E-mail ou CPF já cadastrado", "USER_ALREADY_EXISTS") from None
        return _summary(user)

    # ---- plans ----------------------------------------------------------

    def list_plans(self) -> list[PlanResponse]:
        return [PlanResponse.model_validate(plan) for plan in self._repo.list_plans()]

    def create_plan(self, payload: PlanCreate, actor_id: str) -> PlanResponse:
        if self._repo.get_plan_by_code(payload.code) is not None:
            raise _conflict("Código de plano já cadastrado", "PLAN_ALREADY_EXISTS")
        data = payload.model_dump()
        legacy_price = data.pop("price_cents")
        legacy_currency = data.pop("currency")
        legacy_seat_limit = data.pop("seat_limit")
        legacy_overage = data.pop("overage_cents_per_seat")
        data.pop("trial_days")
        plan = Plan(
            **data,
            price_cents=legacy_price if legacy_price is not None else data["base_price_cents"],
            currency=legacy_currency,
            seat_limit=(
                legacy_seat_limit if legacy_seat_limit is not None else data["included_seats"]
            ),
            overage_cents_per_seat=(
                legacy_overage if legacy_overage is not None else data["price_per_seat_cents"]
            ),
            trial_days=payload.trial_days,
            active=payload.is_active,
        )
        self._repo.add_plan(plan)
        self._audit(
            action="admin.plan.created",
            actor_id=actor_id,
            entity_type="plan",
            target_id=plan.id,
            target_user_id=None,
            before=None,
            after={
                "code": plan.code,
                "is_active": plan.is_active,
                "price_cents": plan.price_cents,
                "trial_days": plan.trial_days,
            },
        )
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("Código de plano já cadastrado", "PLAN_ALREADY_EXISTS") from None
        return PlanResponse.model_validate(plan)

    def update_plan(self, plan_id: str, payload: PlanUpdate, actor_id: str) -> PlanResponse:
        plan = self._repo.get_plan(plan_id)
        if plan is None:
            raise _not_found("Plano não encontrado", "PLAN_NOT_FOUND")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise _bad_request("Nenhum campo para atualizar", "EMPTY_UPDATE")
        before = {key: getattr(plan, key) for key in changes}
        for key, value in changes.items():
            setattr(plan, key, value)
        # Espelhamento legado: as duas visões do plano não podem divergir.
        if "is_active" in changes:
            plan.active = bool(plan.is_active)
        elif "active" in changes:
            plan.is_active = bool(plan.active)
        if "base_price_cents" in changes:
            plan.price_cents = plan.base_price_cents
        elif "price_cents" in changes:
            plan.base_price_cents = plan.price_cents
        if "included_seats" in changes:
            plan.seat_limit = plan.included_seats
        elif "seat_limit" in changes:
            plan.included_seats = plan.seat_limit
        if "price_per_seat_cents" in changes:
            plan.overage_cents_per_seat = plan.price_per_seat_cents
        elif "overage_cents_per_seat" in changes:
            plan.price_per_seat_cents = plan.overage_cents_per_seat
        after = {**before, **{key: getattr(plan, key) for key in changes}}
        after.update(
            {
                "active": bool(plan.active),
                "is_active": bool(plan.is_active),
                "price_cents": plan.price_cents,
                "base_price_cents": plan.base_price_cents,
            }
        )
        self._audit(
            action="admin.plan.updated",
            actor_id=actor_id,
            entity_type="plan",
            target_id=plan.id,
            target_user_id=None,
            before=_redact(before),
            after=_redact(after),
        )
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("Código de plano já cadastrado", "PLAN_ALREADY_EXISTS") from None
        return PlanResponse.model_validate(plan)

    # ---- settings -------------------------------------------------------

    def list_settings(self) -> list[SystemSettingResponse]:
        return [SystemSettingResponse.model_validate(item) for item in self._repo.list_settings()]

    def update_setting(
        self, key: str, payload: SystemSettingUpdate, actor_id: str
    ) -> SystemSettingResponse:
        if not key.strip() or len(key) > 200:
            raise _bad_request("Chave de configuração inválida", "INVALID_SETTING_KEY")
        incoming = {"value": payload.value, "description": payload.description}
        if _SECRET_KEY_RE.search(key) or _contains_sensitive(incoming):
            raise _bad_request(
                "Chaves de segredo e dados pessoais não são configuráveis por esta rota",
                "SECRET_VALUE_REJECTED",
            )
        setting = self._repo.get_setting(key)
        before = (
            None
            if setting is None
            else {"value": dict(setting.value), "description": setting.description}
        )
        if setting is None:
            setting = SystemSetting(key=key, value=payload.value)
            self._repo.add_system_setting(setting)
        else:
            setting.value = payload.value
        if payload.description is not None:
            setting.description = payload.description
        setting.updated_by = actor_id
        self._audit(
            action="admin.setting.updated",
            actor_id=actor_id,
            entity_type="system_setting",
            target_id=key,
            target_user_id=None,
            before=_redact(before),
            after=_redact({"value": payload.value, "description": setting.description}),
        )
        try:
            self._repo.commit()
        except IntegrityError:
            self._repo.rollback()
            raise _conflict("Configuração já existe", "SETTING_ALREADY_EXISTS") from None
        return SystemSettingResponse.model_validate(setting)

    # ---- audit ----------------------------------------------------------

    def _audit(
        self,
        *,
        action: str,
        actor_id: str,
        entity_type: str,
        target_id: str,
        target_user_id: str | None,
        before: dict | None,
        after: dict | None,
    ) -> None:
        """Evento `scope='system'` no mesmo commit da mutação (ADR 0003 v)."""
        actor = self._repo.get_user_by_id(actor_id)
        actor_version = None if actor is None else int(getattr(actor, "permission_version", 1) or 1)
        self._repo.add_audit_event(
            AuditEvent(
                scope="system",
                actor_user_id=actor_id,
                actor_type="internal_admin",
                actor_role="internal_admin",
                permission_version=actor_version,
                action=action,
                entity_type=entity_type,
                entity_id=target_id,
                target_user_id=target_user_id,
                before=before,
                after=after,
                result="success",
            )
        )
