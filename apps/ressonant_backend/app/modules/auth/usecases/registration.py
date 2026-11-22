"""Orquestração do cadastro atômico do plano mestre (§5.1)."""

import hashlib
import json
import re
import secrets
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.common.email import build_invite_url
from app.common.email_outbox import enqueue_email
from app.common.exceptions import ConflictException
from app.config.settings import get_settings
from app.modules.auth.schemas.dto import (
    OrganizacaoResponse,
    RegistrationCreate,
    RegistrationInviteResponse,
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
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import TeamMember
from app.modules.teams.schemas.dto import TeamCreate
from app.modules.teams.usecases.services import TeamService
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from app.modules.user.schemas.dto import UserResponse
from app.modules.user.usecases.services import UserService
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from app.modules.workspace.schemas.dto import WorkspaceCreate
from app.modules.workspace.usecases.services import WorkspaceService
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import ExceptionData, NotFoundException
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

    def register_invited_user(self, payload):
        """Cria apenas identidade global e aceita convite existente; sem org/workspace novo."""
        import hashlib
        from datetime import UTC, datetime

        from app.common.security import hash_password
        from app.modules.organization.domain.models import OrganizationMember
        from app.modules.workspace.domain.models import WorkspaceMember

        token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        try:
            q = self._db.query(Invitation).filter(Invitation.token_hash == token_hash)
            bind = self._db.get_bind()
            if getattr(bind.dialect, "supports_for_update", False):
                q = q.with_for_update()
            invitation = q.first()
            if invitation is None:
                raise NotFoundException(
                    ExceptionData(
                        message="Convite não encontrado", error_code="INVITATION_NOT_FOUND"
                    ),
                    is_expected=True,
                )

            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if invitation.accepted_at is not None:
                raise ConflictException(
                    ExceptionData(
                        message="Convite já aceito", error_code="INVITATION_ALREADY_USED"
                    ),
                    is_expected=True,
                )
            if invitation.revoked_at is not None:
                raise ConflictException(
                    ExceptionData(message="Convite revogado", error_code="INVITATION_REVOKED"),
                    is_expected=True,
                )
            if getattr(invitation, "declined_at", None) is not None:
                raise ConflictException(
                    ExceptionData(message="Convite recusado", error_code="INVITATION_DECLINED"),
                    is_expected=True,
                )
            if expires_at <= now:
                raise ConflictException(
                    ExceptionData(message="Convite expirado", error_code="INVITATION_EXPIRED"),
                    is_expected=True,
                )

            email = invitation.email.strip().lower()
            existing = self._db.query(User).filter(User.email == email).first()
            if existing is not None:
                raise ConflictException(
                    ExceptionData(
                        message=(
                            "Já existe uma conta com este e-mail. "
                            "Faça login para aceitar o convite."
                        ),
                        error_code="USER_ALREADY_EXISTS",
                    ),
                    is_expected=True,
                )

            from app.modules.organization.dataproviders.repository import OrganizationRepository

            org_repo = OrganizationRepository(self._db)
            org = org_repo.lock_organization(invitation.organization_id)
            if org is None:
                raise NotFoundException(
                    ExceptionData(
                        message="Organização não encontrada", error_code="ORGANIZATION_NOT_FOUND"
                    ),
                    is_expected=True,
                )

            limit, plan_name = org_repo.get_seat_limit(invitation.organization_id)
            if limit is not None:
                seats_used = org_repo.count_seats_used(invitation.organization_id)
                if seats_used + 1 > limit:
                    raise ConflictException(
                        ExceptionData(
                            message=(
                                f"O plano {plan_name} permite {limit} seats; "
                                f"{seats_used} de {limit} estão em uso."
                            ),
                            error_code="SEAT_LIMIT_EXCEEDED",
                        ),
                        is_expected=True,
                    )

            cpf_digits = "".join(ch for ch in payload.cpf if ch.isdigit())
            tel_digits = "".join(ch for ch in payload.telefone if ch.isdigit())
            user = User(
                email=email,
                senha_hash=hash_password(payload.senha),
                cpf=cpf_digits,
                telefone=tel_digits,
                idade=payload.idade,
                termos_contrato=payload.termos_contrato,
                status_ativo=True,
                interno_adm=False,
            )
            user.name = payload.nome_completo.strip()
            self._db.add(user)
            self._db.flush()

            org_member = self._db.get(OrganizationMember, (invitation.organization_id, user.id))
            ws_member = (
                self._db.query(WorkspaceMember)
                .filter(
                    WorkspaceMember.workspace_id == invitation.workspace_id,
                    WorkspaceMember.user_id == user.id,
                )
                .first()
            )
            org_role = "admin" if invitation.role == "admin" else "member"
            ws_role = "admin" if invitation.role == "admin" else "member"
            created_org = org_member is None
            created_ws = ws_member is None
            if org_member is None:
                self._db.add(
                    OrganizationMember(
                        organization_id=invitation.organization_id,
                        user_id=user.id,
                        role=org_role,
                        status="active",
                    )
                )
            if ws_member is None:
                self._db.add(
                    WorkspaceMember(
                        workspace_id=invitation.workspace_id, user_id=user.id, role=ws_role
                    )
                )

            team_member_created = False
            channel_member_added = False
            team_repo = TeamRepository(self._db)
            default_team = team_repo.get_default_for_workspace(invitation.workspace_id)
            if default_team is not None and team_repo.is_member(default_team.id, user.id) is None:
                self._db.add(
                    TeamMember(
                        team_id=default_team.id,
                        user_id=user.id,
                        role="admin" if invitation.role == "admin" else "member",
                    )
                )
                team_member_created = True

            channel_repo = ChannelRepository(self._db)
            default_channel = channel_repo.get_default_for_workspace(invitation.workspace_id)
            if default_channel is not None:
                try:
                    members = json.loads(default_channel.member_ids or "[]")
                    if not isinstance(members, list):
                        members = []
                except Exception:
                    members = []
                members = [m for m in members if isinstance(m, str)]
                if user.id not in members:
                    members.append(user.id)
                    default_channel.member_ids = json.dumps(members)
                    self._db.add(default_channel)
                    channel_member_added = True

            invitation.accepted_at = now
            self._db.add(
                AuditEvent(
                    organization_id=invitation.organization_id,
                    workspace_id=invitation.workspace_id,
                    scope="organization",
                    actor_user_id=user.id,
                    actor_type="user",
                    action="invitation.accepted_with_registration",
                    entity_type="invitation",
                    entity_id=invitation.id,
                    result="success",
                    after={
                        "organization_member_created": created_org,
                        "workspace_member_created": created_ws,
                        "team_member_created": team_member_created,
                        "channel_member_added": channel_member_added,
                        "role": invitation.role,
                    },
                    metadata_={"email": invitation.email, "role": invitation.role},
                )
            )
            self._db.commit()
            return user, invitation
        except Exception:
            self._db.rollback()
            raise

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

            created_invites: list[Invitation] = []
            settings = get_settings()
            for convidado in payload.convidados:
                email = convidado.email.strip().lower()
                pending = org_repo.get_pending_invitation(
                    organization_id=organization.id, workspace_id=workspace.id, email=email
                )
                now = datetime.now(UTC)
                if pending is not None and pending.accepted_at is None and pending.revoked_at is None and getattr(pending, "declined_at", None) is None:
                    expires_at = pending.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=UTC)
                    if expires_at > now:
                        continue
                token = secrets.token_urlsafe(32)
                invitation = Invitation(
                    organization_id=organization.id,
                    workspace_id=workspace.id,
                    email=email,
                    role="admin" if convidado.role == "admin" else "member",
                    token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    expires_at=now + timedelta(days=7),
                    invited_by_id=user.id,
                    send_status="pending",
                )
                org_repo.add_invitation(invitation)
                billing_repo.add_audit_event(
                    AuditEvent(
                        organization_id=organization.id,
                        workspace_id=workspace.id,
                        scope="organization",
                        actor_user_id=user.id,
                        actor_type="user",
                        actor_role="owner",
                        action="invitation.created",
                        entity_type="invitation",
                        entity_id=invitation.id,
                        result="success",
                        after={"status": "pending", "source": "registration"},
                        metadata_={"email": email, "role": invitation.role},
                    )
                )
                invite_url = build_invite_url(settings.frontend_base_url, token)
                email_sent = False
                if settings.email_enabled and settings.smtp_host:
                    dedupe_key = (
                        f"invitation.created:{invitation.id}:"
                        f"{hashlib.sha256(token.encode('utf-8')).hexdigest()}"
                    )
                    enqueue_email(
                        self._db,
                        event_type="invitation.created",
                        recipient_email=email,
                        subject="Convite para o Ressonant",
                        payload={
                            "invite_url": invite_url,
                            "workspace_name": workspace.name,
                            "organization_name": organization.name,
                            "inviter_name": user.name or user.email,
                            "role": invitation.role,
                            "expires_at": invitation.expires_at.isoformat(),
                            "invitation_id": invitation.id,
                        },
                        dedupe_key=dedupe_key,
                    )
                    invitation.send_status = "pending"
                else:
                    invitation.send_status = "not_configured"
                created_invites.append((invitation, token, invite_url, email_sent))

            try:
                self._db.commit()
            except IntegrityError:
                raise _registration_failed() from None
        except Exception:
            self._db.rollback()
            raise

        billing_data = billing.get_billing(organization.id, user)
        settings = get_settings()
        invite_responses = []
        for invitation, token, invite_url, email_sent in created_invites:
            dev = settings.environment == "development"
            invite_responses.append(
                RegistrationInviteResponse(
                    id=invitation.id,
                    email=invitation.email,
                    role=invitation.role,
                    status="pending",
                    token=token if dev else None,
                    invite_url=invite_url if dev else None,
                    email_sent=email_sent,
                )
            )
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
            convites=invite_responses,
        )
