from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from app.common.exceptions import ConflictException
from app.modules.billing.dataproviders.repository import BillingRepository
from app.modules.billing.domain.gateway import BillingGateway
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.billing.schemas.dto import (
    BillingResponse,
    PlanResponse,
    SubscriptionResponse,
)
from app.modules.user.domain.models import User
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import ExceptionData, ForbiddenException, NotFoundException
from sqlalchemy.exc import IntegrityError

_BILLING_MANAGE_ROLES = frozenset({"owner", "billing_owner"})
_DEFAULT_PLAN_CODE = "inicial"
_TRANSITIONS: dict[str, frozenset[str]] = {
    "trialing": frozenset({"active"}),
    "active": frozenset({"past_due", "canceled"}),
    "past_due": frozenset({"active", "canceled"}),
    "canceled": frozenset(),
}
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "senha",
        "token",
        "secret",
        "cpf",
        "telefone",
        "email",
        "authorization",
    }
)


class BillingService:
    """Regras de billing local: nenhuma cobrança, nenhuma chamada externa."""

    def __init__(self, repo: BillingRepository, gateway: BillingGateway) -> None:
        self._repo = repo
        self._gateway = gateway

    @staticmethod
    def _forbidden(
        message: str,
        *,
        required: str,
        error_code: str = "BILLING_ACCESS_DENIED",
    ) -> ForbiddenException:
        return ForbiddenException(
            ExceptionData(
                message=message,
                error_code=error_code,
                error_layer="billing",
                required_capability=required,
            ),
            is_expected=True,
        )

    @staticmethod
    def _not_found(message: str, error_code: str) -> NotFoundException:
        return NotFoundException(
            ExceptionData(message=message, error_code=error_code), is_expected=True
        )

    @staticmethod
    def _conflict(message: str, error_code: str) -> ConflictException:
        return ConflictException(
            ExceptionData(message=message, error_code=error_code, error_layer="domain"),
            is_expected=True,
        )

    @staticmethod
    def _redact(payload: dict | None) -> dict | None:
        if payload is None:
            return None
        return {
            key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else value
            for key, value in payload.items()
        }

    def _authorize(
        self,
        organization_id: str,
        actor: User,
        required: Literal["billing.view", "billing.manage"],
        reason: str | None = None,
    ) -> tuple[str, dict | None]:
        """Cinco eixos: papel organizacional é o dono da decisão; adm é break-glass."""
        role = self._repo.get_organization_role(organization_id, actor.id)
        if role in _BILLING_MANAGE_ROLES:
            return role, None
        if actor.interno_adm:
            # R10: break-glass só quando não há membership operacional.
            if role is not None:
                return "interno_adm", None
            if required == "billing.manage" and not (reason and reason.strip()):
                raise self._forbidden(
                    "Ação de interno_adm fora da organização exige justificativa (break-glass).",
                    required="billing.break_glass_reason",
                    error_code="BREAK_GLASS_REASON_REQUIRED",
                )
            metadata: dict = {"interno_adm": True, "break_glass": True}
            if reason and reason.strip():
                metadata["reason"] = reason.strip()
            return "interno_adm", metadata
        raise self._forbidden(
            "Você não tem acesso de billing a esta organização.", required=required
        )

    def _require_organization(self, organization_id: str) -> None:
        if self._repo.get_organization(organization_id) is None:
            raise self._not_found("Organização não encontrada", "ORGANIZATION_NOT_FOUND")

    def _resolve_plan(self, code: str) -> Plan:
        plan = self._repo.get_plan_by_code(code)
        if plan is None:
            raise self._not_found("Plano não encontrado", "PLAN_NOT_FOUND")
        return plan

    def _check_seat_limit(self, organization_id: str, plan: Plan, seats_purchased: int) -> None:
        if plan.seat_limit is None:
            return
        seats_used = self._repo.count_seats_used(organization_id)
        if seats_used > plan.seat_limit + seats_purchased:
            raise self._conflict(
                f"O plano {plan.name} permite {plan.seat_limit} seats; "
                f"{seats_used} de {plan.seat_limit + seats_purchased} estão em uso.",
                "SEAT_LIMIT_EXCEEDED",
            )

    @staticmethod
    def _plan_response(plan: Plan) -> PlanResponse:
        return PlanResponse(
            code=plan.code,
            name=plan.name,
            price_cents=plan.price_cents,
            currency=plan.currency,
            seat_limit=plan.seat_limit,
            overage=plan.overage_cents_per_seat,
            trial_days=plan.trial_days,
            active=plan.active,
        )

    @staticmethod
    def _subscription_response(
        row: tuple[Subscription, Plan] | None,
    ) -> SubscriptionResponse | None:
        if row is None:
            return None
        subscription, _ = row
        return SubscriptionResponse(
            status=subscription.status,
            seats_purchased=subscription.seats_purchased,
            trial_ends_at=subscription.trial_ends_at,
            current_period_end=subscription.current_period_end,
            gateway_ref=subscription.gateway_ref,
        )

    def _build_response(self, organization_id: str) -> BillingResponse:
        row = self._repo.get_subscription_for_display(organization_id)
        plan = row[1] if row is not None else self._resolve_plan(_DEFAULT_PLAN_CODE)
        return BillingResponse(
            organization_id=organization_id,
            plan=self._plan_response(plan),
            subscription=self._subscription_response(row),
            seats_used=self._repo.count_seats_used(organization_id),
        )

    def _audit(
        self,
        *,
        organization_id: str,
        actor: User,
        actor_role: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict | None,
        after: dict | None,
        request_id: str | None,
        break_glass: dict | None,
    ) -> None:
        self._repo.add_audit_event(
            AuditEvent(
                organization_id=organization_id,
                scope="organization",
                actor_user_id=actor.id,
                actor_type="internal_admin" if actor.interno_adm else "user",
                actor_role=actor_role,
                permission_version=self._repo.permission_version_for_organization(organization_id),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id,
                before=self._redact(before),
                after=self._redact(after),
                metadata_=break_glass,
                result="success",
            )
        )

    def get_billing(
        self,
        organization_id: str,
        actor: User,
        *,
        reason: str | None = None,
    ) -> BillingResponse:
        self._authorize(organization_id, actor, "billing.view", reason)
        self._require_organization(organization_id)
        return self._build_response(organization_id)

    def update_billing(
        self,
        organization_id: str,
        actor: User,
        *,
        plan_code: str | None = None,
        seats_purchased: int | None = None,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> BillingResponse:
        role, break_glass = self._authorize(organization_id, actor, "billing.manage", reason)
        self._require_organization(organization_id)
        row = self._repo.get_active_subscription(organization_id)
        if row is None:
            raise self._not_found("Assinatura ativa não encontrada", "SUBSCRIPTION_NOT_FOUND")
        subscription, current_plan = row
        new_plan = self._resolve_plan(plan_code) if plan_code is not None else current_plan
        new_seats = subscription.seats_purchased if seats_purchased is None else seats_purchased
        # Validação antes de qualquer mutação: nada é gravado quando falha.
        self._check_seat_limit(organization_id, new_plan, new_seats)
        before = {
            "plan_code": current_plan.code,
            "seats_purchased": subscription.seats_purchased,
        }
        after = {"plan_code": new_plan.code, "seats_purchased": new_seats}
        try:
            subscription.plan_id = new_plan.id
            subscription.seats_purchased = new_seats
            self._audit(
                organization_id=organization_id,
                actor=actor,
                actor_role=role,
                action="billing.updated",
                entity_type="subscription",
                entity_id=subscription.id,
                before=before,
                after=after,
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return self._build_response(organization_id)

    def create_subscription(
        self,
        organization_id: str,
        actor: User,
        *,
        plan_code: str | None = None,
        seats_purchased: int | None = None,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> BillingResponse:
        role, break_glass = self._authorize(organization_id, actor, "billing.manage", reason)
        self._require_organization(organization_id)
        if self._repo.get_active_subscription(organization_id) is not None:
            raise self._conflict(
                "A organização já possui uma assinatura ativa.", "SUBSCRIPTION_ALREADY_ACTIVE"
            )
        plan = self._resolve_plan(plan_code or _DEFAULT_PLAN_CODE)
        seats = 0 if seats_purchased is None else seats_purchased
        self._check_seat_limit(organization_id, plan, seats)
        intent = self._gateway.create_subscription_intent(
            organization_id=organization_id, plan_code=plan.code, seats_purchased=seats
        )
        if not intent.confirmed:
            raise self._conflict("Intenção de assinatura não confirmada", "BILLING_INTENT_REJECTED")
        now = datetime.now(UTC)
        subscription = Subscription(
            organization_id=organization_id,
            plan_id=plan.id,
            status="trialing",
            seats_purchased=seats,
            trial_ends_at=now + timedelta(days=plan.trial_days),
            current_period_start=now,
            current_period_end=now + timedelta(days=plan.trial_days),
            gateway_ref=intent.gateway_ref,
        )
        try:
            self._repo.add_subscription(subscription)
            self._audit(
                organization_id=organization_id,
                actor=actor,
                actor_role=role,
                action="billing.subscription.created",
                entity_type="subscription",
                entity_id=subscription.id,
                before=None,
                after={
                    "plan_code": plan.code,
                    "status": subscription.status,
                    "seats_purchased": seats,
                    "gateway_ref": subscription.gateway_ref,
                },
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
        except IntegrityError as exc:
            self._repo.rollback()
            raise self._conflict(
                "A organização já possui uma assinatura ativa.", "SUBSCRIPTION_ALREADY_ACTIVE"
            ) from exc
        except Exception:
            self._repo.rollback()
            raise
        return self._build_response(organization_id)

    def update_subscription_status(
        self,
        organization_id: str,
        actor: User,
        *,
        status: str,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> BillingResponse:
        role, break_glass = self._authorize(organization_id, actor, "billing.manage", reason)
        self._require_organization(organization_id)
        # Inclui canceladas para devolver 409 de transição inválida, não 404.
        row = self._repo.get_subscription_for_display(organization_id)
        if row is None:
            raise self._not_found("Assinatura não encontrada", "SUBSCRIPTION_NOT_FOUND")
        subscription, _ = row
        if status not in _TRANSITIONS[subscription.status]:
            raise self._conflict(
                f"Transição de {subscription.status} para {status} não permitida.",
                "INVALID_SUBSCRIPTION_TRANSITION",
            )
        before = {"status": subscription.status}
        try:
            subscription.status = status
            self._audit(
                organization_id=organization_id,
                actor=actor,
                actor_role=role,
                action="billing.subscription.status_changed",
                entity_type="subscription",
                entity_id=subscription.id,
                before=before,
                after={"status": status},
                request_id=request_id,
                break_glass=break_glass,
            )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
        return self._build_response(organization_id)
