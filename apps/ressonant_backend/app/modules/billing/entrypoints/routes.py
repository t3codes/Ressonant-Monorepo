from typing import Annotated

from app.modules.auth.deps import AdminUser, CurrentUser
from app.modules.billing.deps import get_billing_service
from app.modules.billing.schemas.dto import (
    BillingResponse,
    BillingUpdateRequest,
    PlanCatalogResponse,
    PlanCreateRequest,
    PlanResponse,
    PlanUpdateRequest,
    SubscriptionCreateRequest,
    SubscriptionStatusUpdateRequest,
)
from app.modules.billing.usecases.services import BillingService
from fastapi import APIRouter, Depends, Path, Request, status

router = APIRouter(prefix="/organizations/{organization_id}/billing", tags=["billing"])
plans_router = APIRouter(prefix="/plans", tags=["plans"])
Service = Annotated[BillingService, Depends(get_billing_service)]
PlanCode = Annotated[str, Path(min_length=1, max_length=20, pattern=r"^[a-z][a-z0-9_]{0,19}$")]


def _request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


def _break_glass_reason(request: Request) -> str | None:
    return request.headers.get("x-break-glass-reason")


@router.get("", response_model=BillingResponse)
def get_billing(
    organization_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> BillingResponse:
    return service.get_billing(organization_id, current_user, reason=_break_glass_reason(request))


@router.patch("", response_model=BillingResponse)
def update_billing(
    organization_id: str,
    payload: BillingUpdateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> BillingResponse:
    return service.update_billing(
        organization_id,
        current_user,
        plan_code=payload.plan_code,
        seats_purchased=payload.seats_purchased,
        request_id=_request_id(request),
        reason=_break_glass_reason(request),
    )


@router.post("/subscription", response_model=BillingResponse, status_code=201)
def create_subscription(
    organization_id: str,
    request: Request,
    service: Service,
    current_user: CurrentUser,
    payload: SubscriptionCreateRequest | None = None,
) -> BillingResponse:
    return service.create_subscription(
        organization_id,
        current_user,
        plan_code=payload.plan_code if payload else None,
        seats_purchased=payload.seats_purchased if payload else None,
        request_id=_request_id(request),
        reason=_break_glass_reason(request),
    )


@router.patch("/subscription/status", response_model=BillingResponse)
def update_subscription_status(
    organization_id: str,
    payload: SubscriptionStatusUpdateRequest,
    request: Request,
    service: Service,
    current_user: CurrentUser,
) -> BillingResponse:
    return service.update_subscription_status(
        organization_id,
        current_user,
        status=payload.status,
        request_id=_request_id(request),
        reason=_break_glass_reason(request),
    )


@plans_router.get("", response_model=PlanCatalogResponse)
def list_plans(service: Service) -> PlanCatalogResponse:
    """Catálogo público: só ativos; `Authorization`, se enviado, é ignorado."""
    return service.list_plans()


@plans_router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreateRequest, _: AdminUser, service: Service) -> PlanResponse:
    """Adiciona plano ao catálogo (somente `interno_adm`; `active=false` por padrão)."""
    return service.create_plan(payload)


@plans_router.patch("/{code}", response_model=PlanResponse)
def update_plan(
    code: PlanCode, payload: PlanUpdateRequest, _: AdminUser, service: Service
) -> PlanResponse:
    """Edita plano do catálogo (somente `interno_adm`; `code` é imutável)."""
    return service.update_plan(code, payload)


@plans_router.delete("/{code}", response_model=PlanResponse)
def deactivate_plan(code: PlanCode, _: AdminUser, service: Service) -> PlanResponse:
    """Desativa plano do catálogo (remoção lógica; somente `interno_adm`)."""
    return service.deactivate_plan(code)
