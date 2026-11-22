"""Cadastro atômico: uma Session, um commit, nenhum registro parcial."""

import json
from typing import Literal

import pytest
from app.common.exceptions import ConflictException
from app.modules.auth.schemas.dto import ConvidadoInput, RegistrationCreate
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
        organizacao={"nome": "Acme Ltda", "slug": slug},
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
        assert (channel.name, channel.slug) == ("geral", "geral")
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
        service: ChannelService, payload: ChannelCreate, created_by: str
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


def test_register_accepts_convidados_without_creating_invitations(
    session_factory: sessionmaker[Session],
) -> None:
    """Limitação explícita: convites são B2.6; a transação de §5.1 não inclui invitations."""
    _seed_plans(session_factory)
    convidados = [
        ConvidadoInput(email="convite1@example.com", role="admin", nome="Primeiro convite"),
        ConvidadoInput(email="convite2@example.com"),
    ]

    with session_factory() as db:
        response = RegistrationService(db).register(_payload(convidados=convidados))

    with session_factory() as db:
        assert _count_in(db, Invitation) == 0
        assert _count_in(db, User) == 1
    assert response.member_ids == [response.user.id]
