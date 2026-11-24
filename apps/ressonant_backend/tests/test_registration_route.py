"""Testes da rota POST /auth/register após o contrato atômico."""

import json

import pytest
from app.modules.billing.dataproviders.repository import BillingRepository
from app.modules.chat.domain.models import Channel
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, register_payload


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _assert_no_personal_data(response) -> None:
    serialized = json.dumps(response.json(), ensure_ascii=False).lower()
    for forbidden in ("ana@ressonant.dev", "52998224725", "529.982.247-25", "11987654321"):
        assert forbidden not in serialized


def test_register_route_returns_registration_response_and_persists(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    for key in (
        "user",
        "organizacao",
        "assinatura",
        "workspace_ids",
        "workspace_inicial_id",
        "equipe_inicial_id",
        "seats",
        "member_ids",
    ):
        assert key in body
    user = body["user"]
    assert user["email"] == "ana@ressonant.dev"
    assert user["cpf"] == "52998224725"
    assert user["name"] == "Ana Silva"
    assert user["title"] == "Dono da Empresa"
    assert body["organizacao"]["role"] == "owner"
    assert body["assinatura"]["status"] == "trialing"
    assert body["seats"] == {"plan_code": "equipe", "limit": 15, "used": 1}
    assert body["member_ids"] == [user["id"]]

    with session_factory() as db:
        db_user = db.get(User, user["id"])
        assert db_user is not None
        org = db.scalar(select(Organization).where(Organization.id == body["organizacao"]["id"]))
        assert org is not None
        owner = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user["id"],
            )
        )
        assert owner is not None and owner.role == "owner"
        workspace = db.get(Workspace, body["workspace_inicial_id"])
        assert workspace is not None and workspace.organization_id == org.id
        ws_member = db.scalar(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)
        )
        assert ws_member is not None and ws_member.user_id == user["id"]
        team = db.get(Team, body["equipe_inicial_id"])
        assert team is not None and team.workspace_id == workspace.id
        team_member = db.scalar(select(TeamMember).where(TeamMember.team_id == team.id))
        assert team_member is not None and team_member.user_id == user["id"]
        channel = db.scalar(select(Channel).where(Channel.workspace_id == workspace.id))
        assert channel is not None and channel.name == "geral"
        events = list(
            db.scalars(select(AuditEvent.action).where(AuditEvent.organization_id == org.id))
        )
        assert "organization.created" in events


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"cpf": "111.111.111-11"}, "cpf"),
        ({"nome_completo": "Ana"}, "nome_completo"),
        (
            {"organizacao": {"nome": "Acme Ltda", "slug": "Acme Inválida"}},
            "slug",
        ),
        ({"trial": False}, "trial"),
        (
            {
                "convidados": [
                    {"email": "ana2@ressonant.dev"},
                    {"email": "ANA2@ressonant.dev"},
                ]
            },
            "convidados",
        ),
        ({"campo_desconhecido": "x"}, "campo_desconhecido"),
        ({"termos_contrato": False}, "termos_contrato"),
    ],
)
def test_register_route_rejects_invalid_payload(
    client: TestClient, override: dict[str, object], field: str
) -> None:
    response = client.post("/auth/register", json=register_payload(**override))

    assert response.status_code == 422
    fields = {str(message["loc"][-1]) for message in response.json()["error_messages"]}
    assert field in fields


def test_register_route_rejects_duplicate_email_cpf_and_org_slug(
    client: TestClient,
) -> None:
    first = register_payload()
    created = client.post("/auth/register", json=first)
    assert created.status_code == 201

    same_email = client.post("/auth/register", json=register_payload(cpf=VALID_CPFS[1]))
    assert same_email.status_code == 409

    same_cpf = client.post("/auth/register", json=register_payload(email="outra@ressonant.dev"))
    assert same_cpf.status_code == 409

    same_org_slug = client.post(
        "/auth/register",
        json=register_payload(
            email="terceira@ressonant.dev",
            cpf=VALID_CPFS[2],
            organizacao={
                "nome": "Outra",
                "slug": first["organizacao"]["slug"],
                "corporate_domain": first["organizacao"]["corporate_domain"],
            },
        ),
    )
    assert same_org_slug.status_code == 409


def test_register_route_partial_failure_leaves_no_orphans(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = BillingRepository.add_audit_event

    def fail_on_org_created(self, event):  # type: ignore[no-untyped-def]
        if event.action == "organization.created":
            raise RuntimeError("falha no passo 7")
        return original(self, event)

    monkeypatch.setattr(BillingRepository, "add_audit_event", fail_on_org_created)

    with pytest.raises(RuntimeError, match="falha no passo 7"):
        client.post("/auth/register", json=register_payload())

    with session_factory() as db:
        assert _count(db, User) == 0
        assert _count(db, Organization) == 0
        assert _count(db, OrganizationMember) == 0
        assert _count(db, Workspace) == 0
        assert _count(db, Team) == 0
        assert _count(db, Channel) == 0
        assert _count(db, AuditEvent) == 0


def test_register_route_error_messages_do_not_expose_personal_data(
    client: TestClient,
) -> None:
    invalid_cpf = client.post("/auth/register", json=register_payload(cpf="111.111.111-11"))
    assert invalid_cpf.status_code == 422
    _assert_no_personal_data(invalid_cpf)

    first = client.post("/auth/register", json=register_payload())
    assert first.status_code == 201
    duplicate = client.post("/auth/register", json=register_payload(cpf=VALID_CPFS[1]))
    assert duplicate.status_code == 409
    _assert_no_personal_data(duplicate)
