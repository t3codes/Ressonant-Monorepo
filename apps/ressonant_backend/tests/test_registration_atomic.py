"""Cadastro atômico: uma Session, um commit, nenhum registro parcial."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from app.common.exceptions import ConflictException
from app.modules.auth.schemas.dto import (
    ConvidadoInput,
    InviteRegistrationCreate,
    RegistrationCreate,
)
from app.modules.auth.usecases.registration import RegistrationService, _slugify, _unique_slug
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.chat.domain.models import Channel
from app.modules.chat.schemas.dto import ChannelCreate
from app.modules.chat.usecases.services import ChannelService
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
from common.errors import NotFoundException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, make_user

TABLE_MODELS = (
    User,
    Organization,
    OrganizationMember,
    Subscription,
    Workspace,
    WorkspaceMember,
    Team,
    TeamMember,
    Channel,
    AuditEvent,
    Invitation,
    Plan,
)


def _payload(
    *,
    email: str = "ana@example.com",
    cpf: str = VALID_CPFS[0],
    plano_id: Literal["inicial", "equipe", "empresa"] = "equipe",
    slug: str = "acme",
    convidados: list[ConvidadoInput] | None = None,
) -> RegistrationCreate:
    return RegistrationCreate(
        nome_completo="Ana da Silva",
        cargo="Dono da Empresa",
        email=email,
        senha="senha-forte-1",
        cpf=cpf,
        idade=30,
        termos_contrato=True,
        telefone="11987654321",
        organizacao={"nome": "Acme Ltda", "slug": slug, "corporate_domain": "example.com"},
        plano_id=plano_id,
        trial=True,
        workspace_nome="Acme Ltda",
        equipe_inicial_nome="Engenharia",
        convidados=convidados or [],
    )


def _seed_plans(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        db.add_all(
            [
                Plan(
                    code="inicial",
                    name="Inicial",
                    price_cents=0,
                    currency="BRL",
                    seat_limit=3,
                    trial_days=7,
                    active=True,
                ),
                Plan(
                    code="equipe",
                    name="Equipe",
                    price_cents=4900,
                    currency="BRL",
                    seat_limit=15,
                    trial_days=14,
                    active=True,
                ),
                Plan(
                    code="empresa",
                    name="Empresa",
                    price_cents=7900,
                    currency="BRL",
                    seat_limit=None,
                    trial_days=14,
                    active=True,
                ),
            ]
        )
        db.commit()


def _counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as db:
        return {
            model.__tablename__: db.scalar(select(func.count()).select_from(model)) or 0
            for model in TABLE_MODELS
        }


def _count_in(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_register_persists_all_entities_and_full_response(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_plans(session_factory)

    with session_factory() as db:
        response = RegistrationService(db).register(_payload())

    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "ana@example.com"))
        assert user is not None
        assert user.name == "Ana da Silva"
        assert user.title == "Dono da Empresa"

        organization = db.scalar(select(Organization).where(Organization.slug == "acme"))
        assert organization is not None
        assert organization.name == "Acme Ltda"
        assert organization.corporate_domain == "example.com"

        owner = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.user_id == user.id,
            )
        )
        assert owner is not None
        assert (owner.role, owner.status) == ("owner", "active")

        subscription = db.scalar(
            select(Subscription).where(Subscription.organization_id == organization.id)
        )
        assert subscription is not None
        assert subscription.status == "trialing"

        workspace = db.scalar(select(Workspace).where(Workspace.organization_id == organization.id))
        assert workspace is not None
        assert workspace.slug == "acme-ltda"
        assert workspace.owner_id == user.id

        workspace_member = db.scalar(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)
        )
        assert workspace_member is not None
        assert (workspace_member.user_id, workspace_member.role) == (user.id, "admin")

        team = db.scalar(select(Team).where(Team.workspace_id == workspace.id))
        assert team is not None
        assert team.slug == "engenharia"
        assert team.owner_id == user.id

        team_member = db.scalar(select(TeamMember).where(TeamMember.team_id == team.id))
        assert team_member is not None
        assert (team_member.user_id, team_member.role) == (user.id, "admin")

        channel = db.scalar(select(Channel).where(Channel.workspace_id == workspace.id))
        assert channel is not None
        assert (channel.name, channel.slug) == ("geral", f"geral-{workspace.id}")
        assert channel.name == "geral"
        assert json.loads(channel.member_ids) == [user.id]

        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.organization_id == organization.id)
                .order_by(AuditEvent.action)
            )
        )
        assert [event.action for event in events] == [
            "billing.subscription.created",
            "organization.created",
        ]
        event = events[1]
        assert event.actor_user_id == user.id
        assert event.actor_type == "user"
        assert event.actor_role == "owner"
        assert event.scope == "organization"
        assert event.entity_type == "organization"
        assert event.entity_id == organization.id
        assert event.permission_version == workspace.management_permission_version
        assert event.result == "success"
        assert event.before is None
        assert event.after == {"nome": "Acme Ltda", "slug": "acme", "plano": "equipe"}

    assert response.user.id == user.id
    assert response.user.email == user.email
    assert response.user.name == "Ana da Silva"
    assert response.user.title == "Dono da Empresa"
    assert response.organizacao.id == organization.id
    assert response.organizacao.nome == "Acme Ltda"
    assert response.organizacao.slug == "acme"
    assert response.organizacao.corporate_domain == "example.com"
    assert response.organizacao.role == "owner"
    assert response.assinatura.status == "trialing"
    assert response.assinatura.gateway_ref is not None
    assert response.assinatura.gateway_ref.startswith("stub_")
    assert response.workspace_ids == [workspace.id]
    assert response.workspace_inicial_id == workspace.id
    assert response.equipe_inicial_id == team.id
    assert response.seats.plan_code == "equipe"
    assert response.seats.limit == 15
    assert response.seats.used == 1
    assert response.member_ids == [user.id]


def test_unique_slug_appends_numeric_suffix() -> None:
    used = {"acme-ltda", "acme-ltda-2"}
    assert _slugify("Acme Ltda", "workspace") == "acme-ltda"
    assert _unique_slug("Acme Ltda", "workspace", lambda slug: slug in used) == "acme-ltda-3"


def test_register_failure_at_channel_rolls_back_everything(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_plans(session_factory)
    before = _counts(session_factory)

    def fail_add_channel(
        service: ChannelService, payload: ChannelCreate, created_by: str, *, slug: str | None = None
    ) -> Channel:
        raise RuntimeError("falha ao criar canal")

    monkeypatch.setattr(ChannelService, "add_channel", fail_add_channel)
    with session_factory() as db:
        with pytest.raises(RuntimeError, match="falha ao criar canal"):
            RegistrationService(db).register(_payload())

    assert _counts(session_factory) == before
    assert _counts(session_factory)["invitations"] == 0


def test_register_duplicate_identity_keeps_code_and_writes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_plans(session_factory)
    make_user(session_factory, email="ana@example.com", cpf=VALID_CPFS[1])
    before = _counts(session_factory)

    duplicated = (
        _payload(email="ana@example.com", cpf=VALID_CPFS[0]),
        _payload(email="bia@example.com", cpf=VALID_CPFS[1]),
    )
    for payload in duplicated:
        with session_factory() as db:
            with pytest.raises(ConflictException) as conflict:
                RegistrationService(db).register(payload)
            assert conflict.value.exception_data.error_code == "USER_ALREADY_EXISTS"
            assert str(conflict.value) == "E-mail ou CPF já cadastrado"
        assert _counts(session_factory) == before


def test_register_duplicate_organization_slug_keeps_code_and_writes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_plans(session_factory)
    with session_factory() as db:
        db.add(Organization(name="Outra Acme", slug="acme"))
        db.commit()
    before = _counts(session_factory)

    with session_factory() as db:
        with pytest.raises(ConflictException) as conflict:
            RegistrationService(db).register(_payload())
        assert conflict.value.exception_data.error_code == "ORGANIZATION_ALREADY_EXISTS"
    assert _counts(session_factory) == before


def test_register_missing_plan_keeps_code_and_writes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    before = _counts(session_factory)

    with session_factory() as db:
        with pytest.raises(NotFoundException) as missing:
            RegistrationService(db).register(_payload())
        assert missing.value.exception_data.error_code == "PLAN_NOT_FOUND"
    assert _counts(session_factory) == before


def test_register_commit_integrity_error_uses_expected_copy(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_plans(session_factory)
    before = _counts(session_factory)

    def fail_commit(session: Session) -> None:
        raise IntegrityError("COMMIT", {}, Exception("duplicate key"))

    monkeypatch.setattr(Session, "commit", fail_commit)
    with session_factory() as db:
        with pytest.raises(ConflictException) as conflict:
            RegistrationService(db).register(_payload())
        data = conflict.value.exception_data
        assert data.error_code == "REGISTRATION_FAILED"
        assert data.error_layer == "auth"
        assert str(conflict.value) == (
            "Não foi possível criar sua empresa. Nenhum dado foi salvo. Tente novamente."
        )
    assert _counts(session_factory) == before


def test_register_creates_invitations_for_convidados_in_development(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cadastro do owner cria convites para e-mails convidados; em dev expõe link/token."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    try:
        _seed_plans(session_factory)
        convidados = [
            ConvidadoInput(email="convite1@example.com", role="admin", nome="Primeiro convite"),
            ConvidadoInput(email="convite2@example.com"),
        ]

        with session_factory() as db:
            response = RegistrationService(db).register(_payload(convidados=convidados))

        with session_factory() as db:
            assert _count_in(db, Invitation) == 2
            assert _count_in(db, User) == 1
        assert response.member_ids == [response.user.id]
        assert len(response.convites) == 2
        assert all(c.token for c in response.convites)
        assert all(c.invite_url for c in response.convites)
        assert {c.email for c in response.convites} == {
            "convite1@example.com",
            "convite2@example.com",
        }
    finally:
        get_settings.cache_clear()


def _seed_invitation_context(
    session_factory: sessionmaker[Session],
    *,
    corporate_email: str = "helena.rocha@example.com",
    personal_email: str = "helena.pessoal@example.com",
) -> dict[str, str]:
    """Convite com reserva ativa e duas equipes, para provar o vínculo por team_id."""
    token = uuid.uuid4().hex
    now = datetime.now(UTC)
    with session_factory() as db:
        org = Organization(
            name="Org Convite",
            slug=f"org-{uuid.uuid4().hex[:8]}",
            corporate_domain="example.com",
        )
        db.add(org)
        db.flush()
        owner_email = f"owner-{uuid.uuid4().hex[:8]}@x.com"
        owner = make_user(session_factory, email=owner_email, cpf=VALID_CPFS[3])
        db.add(
            OrganizationMember(
                organization_id=org.id, user_id=owner.id, role="owner", status="active"
            )
        )
        workspace = Workspace(
            name="WS Convite",
            slug=f"ws-{uuid.uuid4().hex[:8]}",
            owner_id=owner.id,
            organization_id=org.id,
        )
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role="admin"))
        suffix = uuid.uuid4().hex[:6]
        default_team = Team(
            name="Equipe Default",
            slug=f"default-{suffix}",
            workspace_id=workspace.id,
            owner_id=owner.id,
            key_prefix="DFT",
            criado_em=now - timedelta(days=1),
        )
        target_team = Team(
            name="Equipe Auditoria",
            slug=f"auditoria-{suffix}",
            workspace_id=workspace.id,
            owner_id=owner.id,
            key_prefix="AUD",
            criado_em=now,
        )
        db.add_all([default_team, target_team])
        db.flush()
        invitation = Invitation(
            organization_id=org.id,
            workspace_id=workspace.id,
            personal_email=personal_email,
            corporate_email=corporate_email,
            invitee_name="Helena Rocha",
            team_id=target_team.id,
            role="member",
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=now + timedelta(days=7),
            invited_by_id=owner.id,
            send_status="pending",
            reservation_active=True,
        )
        db.add(invitation)
        db.commit()
        return {
            "token": token,
            "organization_id": org.id,
            "workspace_id": workspace.id,
            "default_team_id": default_team.id,
            "target_team_id": target_team.id,
            "invitation_id": invitation.id,
        }


def test_register_invited_user_uses_reserved_corporate_email_and_minimal_payload(
    session_factory: sessionmaker[Session],
) -> None:
    ctx = _seed_invitation_context(session_factory)
    payload = InviteRegistrationCreate(
        token=ctx["token"],
        nome_completo="Helena Rocha",
        cpf="529.982.247-25",
        senha="senha-forte-1",
        termos_contrato=True,
    )

    with session_factory() as db:
        user, invitation = RegistrationService(db).register_invited_user(payload)

    with session_factory() as db:
        stored = db.get(User, user.id)
        assert stored is not None
        assert stored.email == "helena.rocha@example.com"
        assert stored.corporate_email == "helena.rocha@example.com"
        assert stored.personal_email == "helena.pessoal@example.com"
        assert stored.cpf == "52998224725"
        assert stored.telefone is None
        assert stored.idade is None

        assert (
            db.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == ctx["organization_id"],
                    OrganizationMember.user_id == stored.id,
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ctx["workspace_id"],
                    WorkspaceMember.user_id == stored.id,
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(TeamMember).where(
                    TeamMember.team_id == ctx["target_team_id"], TeamMember.user_id == stored.id
                )
            )
            is not None
        )
        assert (
            db.scalar(
                select(TeamMember).where(
                    TeamMember.team_id == ctx["default_team_id"], TeamMember.user_id == stored.id
                )
            )
            is None
        )

        stored_invitation = db.get(Invitation, ctx["invitation_id"])
        assert stored_invitation is not None
        assert stored_invitation.accepted_at is not None
        assert stored_invitation.reservation_active is False
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == stored_invitation.id,
                AuditEvent.action == "invitation.accepted_with_registration",
            )
        )
        assert event is not None
        assert event.after["team_id"] == ctx["target_team_id"]
    assert invitation.id == ctx["invitation_id"]


def test_register_invited_user_does_not_require_matching_authored_email(
    session_factory: sessionmaker[Session],
) -> None:
    """A posse do token e o CPF válido bastam, mesmo com conta no e-mail pessoal."""
    personal_email = "dup@example.com"
    ctx = _seed_invitation_context(
        session_factory,
        personal_email=personal_email,
        corporate_email="duplicado.exemplo@example.com",
    )
    make_user(session_factory, email=personal_email, cpf=VALID_CPFS[1])
    payload = InviteRegistrationCreate(
        token=ctx["token"],
        nome_completo="Duplicado Exemplo",
        cpf=VALID_CPFS[2],
        senha="senha-forte-1",
        termos_contrato=True,
    )

    with session_factory() as db:
        user, _ = RegistrationService(db).register_invited_user(payload)

    assert user.email == "duplicado.exemplo@example.com"
    assert user.personal_email == personal_email
