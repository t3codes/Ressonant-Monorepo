from typing import Annotated

from app.modules.admin.deps import get_admin_service
from app.modules.admin.schemas.dto import (
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    SuperuserCreate,
    SuperuserSummary,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from app.modules.admin.usecases.services import AdminService
from app.modules.auth.deps import PlatformAdmin, require_platform_admin
from fastapi import APIRouter, Depends, Path, status

# Guarda de plataforma no roteador: nenhuma rota /admin/* escapa.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)])
Service = Annotated[AdminService, Depends(get_admin_service)]
AdminKey = Annotated[str, Path(min_length=1, max_length=200)]


@router.get("/superusers", response_model=list[SuperuserSummary])
def list_superusers(service: Service) -> list[SuperuserSummary]:
    """Lista superusers; CPF sempre mascarado."""
    return service.list_superusers()


@router.post("/superusers", response_model=SuperuserSummary, status_code=status.HTTP_201_CREATED)
def create_superuser(
    payload: SuperuserCreate, actor: PlatformAdmin, service: Service
) -> SuperuserSummary:
    """Cria ou promove um superuser com auditoria `scope='system'`."""
    return service.create_superuser(payload, actor.id)


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(service: Service) -> list[PlanResponse]:
    """Lista o catálogo completo, inclusive planos inativos."""
    return service.list_plans()


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, actor: PlatformAdmin, service: Service) -> PlanResponse:
    """Adiciona plano ao catálogo global."""
    return service.create_plan(payload, actor.id)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: str, payload: PlanUpdate, actor: PlatformAdmin, service: Service
) -> PlanResponse:
    """Edita plano por id; `code` é imutável."""
    return service.update_plan(plan_id, payload, actor.id)


@router.get("/settings", response_model=list[SystemSettingResponse])
def list_settings(service: Service) -> list[SystemSettingResponse]:
    """Lista configurações globais não secretas."""
    return service.list_settings()


@router.patch("/settings/{key}", response_model=SystemSettingResponse)
def update_setting(
    key: AdminKey, payload: SystemSettingUpdate, actor: PlatformAdmin, service: Service
) -> SystemSettingResponse:
    """Cria/atualiza configuração global; chaves de segredo são rejeitadas."""
    return service.update_setting(key, payload, actor.id)
