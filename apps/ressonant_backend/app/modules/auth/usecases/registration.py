"""Orquestração do cadastro atômico do plano mestre (§5.1)."""

import re
import unicodedata
from collections.abc import Callable

from app.common.exceptions import ConflictException
from app.modules.auth.schemas.dto import (
    OrganizacaoResponse,
    RegistrationCreate,
    RegistrationResponse,
    SeatsResponse,
)
from app.modules.billing.dataproviders.repository import BillingRepository
from app.modules.billing.dataproviders.stub_gateway import StubBillingGateway
from app.modules.billing.usecases.services import BillingService
from app.modules.chat.dataproviders.repository import ChannelRepository
from app.modules.chat.schemas.dto import ChannelCreate
from app.modules.chat.usecases.services import ChannelService
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.schemas.dto import TeamCreate
from app.modules.teams.usecases.services import TeamService
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.schemas.dto import UserResponse
from app.modules.user.usecases.services import UserService
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from app.modules.workspace.schemas.dto import WorkspaceCreate
from app.modules.workspace.usecases.services import WorkspaceService
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import ExceptionData
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _slugify(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return (re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-") or fallback)[:100]


def _unique_slug(value: str, fallback: str, exists: Callable[[str], bool]) -> str:
    base = _slugify(value, fallback)
    slug = base
    counter = 2
    while exists(slug):
        suffix = f"-{counter}"
        slug = f"{base[: 100 - len(suffix)]}{suffix}"
        counter += 1
    return slug


def _organization_conflict() -> ConflictException:
    return ConflictException(
        ExceptionData(
            message="Já existe uma organização com este slug",
            error_code="ORGANIZATION_ALREADY_EXISTS",
        ),
        is_expected=True,
    )


def _registration_failed() -> ConflictException:
    return ConflictException(
        ExceptionData(
            message="Não foi possível criar sua empresa. Nenhum dado foi salvo. Tente novamente.",
            error_code="REGISTRATION_FAILED",
            error_layer="auth",
        ),
        is_expected=True,
    )


class RegistrationService:
    """Cadastro atômico: uma Session compartilhada e um único commit (§5.1)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def register(self, payload: RegistrationCreate) -> RegistrationResponse:
        try:
            user = UserService(UserRepository(self._db)).add_user(payload)
            user.name = payload.nome_completo
            user.title = payload.cargo

            org_repo = OrganizationRepository(self._db)
            if org_repo.exists_by_slug(payload.organizacao.slug):
                raise _organization_conflict()
            organization = org_repo.add(
                Organization(name=payload.organizacao.nome, slug=payload.organizacao.slug)
            )
            org_repo.add_member(
                OrganizationMember(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="owner",
                    status="active",
                )
            )

            billing_repo = BillingRepository(self._db)
            billing = BillingService(billing_repo, StubBillingGateway())
            billing.add_trial_subscription(organization.id, user, plan_code=payload.plano_id)

            workspace_repo = WorkspaceRepository(self._db)
            workspace = WorkspaceService(workspace_repo).add_workspace(
                WorkspaceCreate(
                    name=payload.workspace_nome,
                    slug=_unique_slug(
                        payload.workspace_nome, "workspace", workspace_repo.exists_by_slug
                    ),
                    description=None,
                    organization_id=organization.id,
                ),
                owner_id=user.id,
            )

            team_repo = TeamRepository(self._db)
            team = TeamService(team_repo).add_team(
                TeamCreate(
                    workspace_id=workspace.id,
                    name=payload.equipe_inicial_nome,
                    slug=_unique_slug(
                        payload.equipe_inicial_nome, "equipe", team_repo.exists_by_slug
                    ),
                    description=None,
                ),
                owner_id=user.id,
            )

            ChannelService(ChannelRepository(self._db)).add_channel(
                ChannelCreate(workspace_id=workspace.id, name="geral"),
                created_by=user.id,
                slug=f"geral-{workspace.id}",
            )

            billing_repo.add_audit_event(
                AuditEvent(
                    organization_id=organization.id,
                    scope="organization",
                    actor_user_id=user.id,
                    actor_type="user",
                    actor_role="owner",
                    action="organization.created",
                    entity_type="organization",
                    entity_id=organization.id,
                    permission_version=billing_repo.permission_version_for_organization(
                        organization.id
                    ),
                    result="success",
                    before=None,
                    after={
                        "nome": organization.name,
                        "slug": organization.slug,
                        "plano": payload.plano_id,
                    },
                )
            )

            try:
                self._db.commit()
            except IntegrityError:
                raise _registration_failed() from None
        except Exception:
            self._db.rollback()
            raise

        billing_data = billing.get_billing(organization.id, user)
        return RegistrationResponse(
            user=UserResponse.model_validate(user),
            organizacao=OrganizacaoResponse(
                id=organization.id,
                nome=organization.name,
                slug=organization.slug,
                role="owner",
            ),
            assinatura=billing_data.subscription,
            workspace_ids=[workspace.id],
            workspace_inicial_id=workspace.id,
            equipe_inicial_id=team.id,
            seats=SeatsResponse(
                plan_code=billing_data.plan.code,
                limit=billing_data.plan.seat_limit,
                used=billing_data.seats_used,
            ),
            member_ids=[user.id],
        )
