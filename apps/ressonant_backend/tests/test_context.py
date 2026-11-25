from __future__ import annotations

import uuid

import httpx
import pytest
from app.main import app
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.domain.models import OrganizationMember
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import WorkspaceManagementGrant
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import login, make_user

CPFS = [
    "10433218100",
    "96001338914",
    "08386379499",
    "02654235114",
    "16155940789",
    "81618495950",
    "31034131656",
    "47525534144",
    "92832764851",
]
EMAILS = [
    "owner@ressonant.com",
    "gestor.equipes@ressonant.com",
    "dev.member@ressonant.com",
    "auditor.viewer@ressonant.com",
    "sem.equipe@ressonant.com",
    "externo@empresab.com",
]
MANAGEMENT_FIELDS = (
    "management_read",
    "management_modify",
    "management_grant",
    "teams_create",
    "teams_update",
    "teams_soft_delete",
    "teams_hard_delete",
    "members_manage",
    "columns_manage",
    "blocked_cards_read",
    "blocked_cards_unblock",
    "audit_read",
    "settings_manage",
    "grants_manage",
    "taxonomy_read",
    "taxonomy_manage",
    "taxonomy_manage_grant",
)
TAXONOMY_FIELDS = ("taxonomy_read", "taxonomy_manage", "taxonomy_manage_grant")


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> dict[str, object]:
    users = {
        email: make_user(
            session_factory, email=email, cpf=CPFS[index], admin=(index == 0 and email == EMAILS[0])
        )
        for index, email in enumerate(EMAILS)
    }
    no_link = make_user(session_factory, email="sem.vinculo@ressonant.com", cpf=CPFS[7])

    with session_factory() as db:
        owner = db.get(User, users[EMAILS[0]].id)
        assert owner is not None
        owner.name = "Owner Ressonant"
        owner.title = "Dono da Empresa"

        main = Workspace(
            name="Ressonant Corp",
            slug="ressonant-corp-seed",
            owner_id=owner.id,
            description="Workspace principal de testes RBAC",
        )
        db.add(main)
        db.flush()
        assert main.organization_id is not None
        db.add(
            OrganizationMember(
                organization_id=main.organization_id,
                user_id=users[EMAILS[1]].id,
                role="admin",
                status="active",
            )
        )
        for email in EMAILS[:5]:
            db.add(
                WorkspaceMember(
                    workspace_id=main.id,
                    user_id=users[email].id,
                    role="admin" if email in EMAILS[:2] else "member",
                )
            )

        eng = Team(
            name="Engenharia",
            slug="engenharia-seed",
            key_prefix="ENG",
            workspace_id=main.id,
            owner_id=owner.id,
        )
        plataforma = Team(
            name="Plataforma",
            slug="plataforma-seed",
            key_prefix="PLAT",
            workspace_id=main.id,
            owner_id=owner.id,
        )
        db.add_all((eng, plataforma))
        db.flush()
        for team in (eng, plataforma):
            db.add(TeamMember(team_id=team.id, user_id=owner.id, role="admin"))
        db.add(TeamMember(team_id=eng.id, user_id=users[EMAILS[2]].id, role="member"))
        db.add(TeamMember(team_id=eng.id, user_id=users[EMAILS[3]].id, role="viewer"))

        other = Workspace(
            name="Empresa B - Teste IDOR",
            slug="empresa-b-seed",
            owner_id=users[EMAILS[5]].id,
            description="Workspace isolado",
        )
        db.add(other)
        db.flush()
        db.add(WorkspaceMember(workspace_id=other.id, user_id=users[EMAILS[5]].id, role="admin"))
        equipe_b = Team(
            name="Equipe B",
            slug="equipe-b-seed",
            key_prefix="EQPB",
            workspace_id=other.id,
            owner_id=users[EMAILS[5]].id,
        )
        db.add(equipe_b)
        db.flush()
        db.add(TeamMember(team_id=equipe_b.id, user_id=users[EMAILS[5]].id, role="admin"))
        db.commit()

        return {
            "users": users,
            "no_link": no_link,
            "main_id": main.id,
            "main_org_id": main.organization_id,
            "other_id": other.id,
            "other_org_id": other.organization_id,
            "eng_id": eng.id,
            "plataforma_id": plataforma.id,
            "equipe_b_id": equipe_b.id,
        }


def _get_context(client: TestClient, headers: dict[str, str]) -> tuple[dict, list[str]]:
    seen: list[str] = []

    def record(request: httpx.Request) -> None:
        seen.append(request.url.path)

    client.event_hooks["request"].append(record)
    try:
        response = client.get("/me/context", headers=headers)
    finally:
        client.event_hooks["request"].remove(record)
    assert response.status_code == 200, response.text
    return response.json(), seen


def _db_member_ids(session_factory: sessionmaker[Session], workspace_id: str) -> list[str]:
    with session_factory() as db:
        return list(
            db.scalars(
                select(WorkspaceMember.user_id)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(WorkspaceMember.criado_em, WorkspaceMember.id)
            )
        )


def _db_teams(
    session_factory: sessionmaker[Session], workspace_id: str, user_id: str
) -> list[tuple[str, str, str, str, str]]:
    with session_factory() as db:
        rows = db.execute(
            select(Team, TeamMember.role)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(
                Team.workspace_id == workspace_id,
                TeamMember.user_id == user_id,
                Team.is_deleted.is_(False),
            )
            .order_by(Team.criado_em, Team.id)
        ).all()
        return [(team.id, team.name, team.slug, team.key_prefix, role) for team, role in rows]


def _expected_team(body_team: dict) -> tuple[str, str, str, str, str]:
    return (
        body_team["id"],
        body_team["name"],
        body_team["slug"],
        body_team["key_prefix"],
        body_team["role"],
    )


def test_owner_gets_full_context_from_database_without_users_call(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    owner = seeded["users"][EMAILS[0]]
    main_id = seeded["main_id"]
    assert isinstance(main_id, str)
    headers = login(client, owner.email)
    body, seen = _get_context(client, headers)

    assert set(body) == {
        "user",
        "organizations",
        "active_organization",
        "workspaces",
        "capabilities",
        "subscription",
        "permission_version",
        "workspace_inicial_id",
        "equipe_inicial_id",
        "organizacao",
        "seats",
    }
    assert body["user"]["email"] == owner.email
    assert body["user"]["name"] == "Owner Ressonant"
    assert body["user"]["title"] == "Dono da Empresa"
    assert len(body["organizations"]) == 1
    assert body["organizations"][0] == {
        "id": seeded["main_org_id"],
        "name": "Ressonant Corp",
        "slug": "ressonant-corp-seed",
        "corporate_domain": None,
        "role": "owner",
        "status": "active",
    }
    assert body["active_organization"] == body["organizations"][0]
    assert body["organizacao"] == body["active_organization"]

    assert len(body["workspaces"]) == 1
    workspace = body["workspaces"][0]
    assert workspace["id"] == main_id
    assert workspace["organization_id"] == seeded["main_org_id"]
    assert workspace["role"] == "admin"
    assert workspace["member_ids"] == _db_member_ids(session_factory, main_id)
    assert {_expected_team(team) for team in workspace["teams"]} == set(
        _db_teams(session_factory, main_id, owner.id)
    )
    assert set(workspace["capabilities"]) == set(MANAGEMENT_FIELDS)
    assert all(workspace["capabilities"].values())
    assert body["capabilities"]["management"] == workspace["capabilities"]
    assert body["capabilities"]["billing"] == {"view": True, "manage": True}
    assert body["capabilities"]["domain"] == {"cards_write": True}
    assert body["permission_version"] == workspace["permission_version"]
    assert body["subscription"] is None
    assert body["workspace_inicial_id"] == main_id
    assert body["equipe_inicial_id"] == workspace["teams"][0]["id"]
    assert body["seats"] is None

    assert "/me/context" in seen
    assert not [path for path in seen if path.startswith("/users")]


@pytest.mark.parametrize(
    ("email", "expected_team"),
    [
        (EMAILS[2], ("engenharia-seed", "ENG", "member")),
        (EMAILS[3], ("engenharia-seed", "ENG", "viewer")),
        (EMAILS[4], None),
        (EMAILS[1], None),
    ],
)
def test_members_see_real_workspace_links_and_no_fabricated_teams(
    client: TestClient,
    session_factory: sessionmaker[Session],
    seeded: dict[str, object],
    email: str,
    expected_team: tuple[str, str, str] | None,
) -> None:
    user = seeded["users"][email]
    main_id = seeded["main_id"]
    assert isinstance(main_id, str)
    body, seen = _get_context(client, login(client, email))

    assert len(body["workspaces"]) == 1
    workspace = body["workspaces"][0]
    assert workspace["id"] == main_id
    assert workspace["member_ids"] == _db_member_ids(session_factory, main_id)
    db_teams = _db_teams(session_factory, main_id, user.id)
    assert [_expected_team(team) for team in workspace["teams"]] == db_teams
    if expected_team is None:
        assert workspace["teams"] == []
    else:
        assert len(db_teams) == 1
        assert (db_teams[0][2], db_teams[0][3], db_teams[0][4]) == expected_team
    if email == EMAILS[1]:
        # Matriz §6 do Plano Mestre Unificado: admin da org e do workspace tem
        # gestão até modify; R9 bloqueia apenas a escalada a nível grant.
        assert workspace["capabilities"]["management_read"] is True
        assert workspace["capabilities"]["management_modify"] is True
    else:
        assert not any(
            value for key, value in workspace["capabilities"].items() if key not in TAXONOMY_FIELDS
        )
        assert workspace["capabilities"]["taxonomy_read"] is True
        assert workspace["capabilities"]["taxonomy_manage"] is False
        assert workspace["capabilities"]["taxonomy_manage_grant"] is False
    assert body["capabilities"]["management"] == workspace["capabilities"]
    assert body["capabilities"]["billing"] == {"view": True, "manage": False}
    assert body["capabilities"]["domain"] == {"cards_write": True}
    assert not [path for path in seen if path.startswith("/users")]


def test_non_owner_without_organization_membership_derives_member_role(
    client: TestClient, seeded: dict[str, object]
) -> None:
    body, _ = _get_context(client, login(client, EMAILS[2]))

    assert body["organizations"] == [
        {
            "id": seeded["main_org_id"],
            "name": "Ressonant Corp",
            "slug": "ressonant-corp-seed",
            "corporate_domain": None,
            "role": "member",
            "status": "active",
        }
    ]
    assert body["active_organization"] == body["organizations"][0]


def test_external_user_only_sees_own_isolated_workspace(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    other_id = seeded["other_id"]
    assert isinstance(other_id, str)
    body, _ = _get_context(client, login(client, EMAILS[5]))

    assert body["organizations"] == [
        {
            "id": seeded["other_org_id"],
            "name": "Empresa B - Teste IDOR",
            "slug": "empresa-b-seed",
            "corporate_domain": None,
            "role": "owner",
            "status": "active",
        }
    ]
    assert [workspace["id"] for workspace in body["workspaces"]] == [other_id]
    workspace = body["workspaces"][0]
    assert workspace["member_ids"] == _db_member_ids(session_factory, other_id)
    assert [_expected_team(team) for team in workspace["teams"]] == _db_teams(
        session_factory, other_id, seeded["users"][EMAILS[5]].id
    )
    assert seeded["main_id"] not in [workspace["id"] for workspace in body["workspaces"]]
    assert "ressonant-corp-seed" not in str(body["workspaces"])
    assert body["capabilities"]["billing"] == {"view": True, "manage": True}


def test_user_without_membership_returns_empty_lists_and_denied_capabilities(
    client: TestClient, seeded: dict[str, object]
) -> None:
    body, seen = _get_context(client, login(client, "sem.vinculo@ressonant.com"))

    assert body["organizations"] == []
    assert body["active_organization"] is None
    assert body["workspaces"] == []
    assert body["subscription"] is None
    assert body["workspace_inicial_id"] is None
    assert body["equipe_inicial_id"] is None
    assert body["organizacao"] is None
    assert body["seats"] is None
    assert body["permission_version"] == 1
    assert not any(body["capabilities"]["management"].values())
    assert body["capabilities"]["billing"] == {"view": False, "manage": False}
    assert body["capabilities"]["domain"] == {"cards_write": False}
    assert "ressonant-corp-seed" not in str(body)
    assert "empresa-b-seed" not in str(body)
    assert not [path for path in seen if path.startswith("/users")]


def test_team_membership_alone_enables_card_writes_without_leaking_workspace(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    user = make_user(session_factory, email="team.only@ressonant.dev", cpf=CPFS[8])
    with session_factory() as db:
        db.add(TeamMember(team_id=seeded["eng_id"], user_id=user.id, role="member"))
        db.commit()

    body, _ = _get_context(client, login(client, user.email))

    assert body["workspaces"] == []
    assert body["organizations"] == []
    assert body["capabilities"]["domain"] == {"cards_write": True}


def test_management_capabilities_are_union_and_permission_version_is_max(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    # Usa um membro sem papel na org e sem admin de workspace para que o grant
    # `read` seja o único determinante das capabilities (matriz §6).
    member_id = seeded["users"][EMAILS[4]].id
    with session_factory() as db:
        db.add(
            WorkspaceManagementGrant(
                workspace_id=seeded["main_id"],
                user_id=member_id,
                level="read",
                granted_by_id=seeded["users"][EMAILS[0]].id,
            )
        )
        db.add(WorkspaceMember(workspace_id=seeded["other_id"], user_id=member_id, role="member"))
        other = db.get(Workspace, seeded["other_id"])
        assert other is not None
        other.management_permission_version = 7
        db.commit()

    body, _ = _get_context(client, login(client, EMAILS[4]))

    assert len(body["workspaces"]) == 2
    read_only = next(
        workspace for workspace in body["workspaces"] if workspace["id"] == seeded["main_id"]
    )
    no_grant = next(
        workspace for workspace in body["workspaces"] if workspace["id"] == seeded["other_id"]
    )
    assert read_only["capabilities"]["management_read"] is True
    assert read_only["capabilities"]["management_modify"] is False
    assert not any(
        value for key, value in no_grant["capabilities"].items() if key not in TAXONOMY_FIELDS
    )
    assert no_grant["capabilities"]["taxonomy_read"] is True
    assert no_grant["capabilities"]["taxonomy_manage"] is False
    assert no_grant["capabilities"]["taxonomy_manage_grant"] is False
    assert body["capabilities"]["management"]["management_read"] is True
    assert body["capabilities"]["management"]["management_modify"] is False
    assert body["permission_version"] == 7


def test_subscription_is_exposed_from_active_organization(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    with session_factory() as db:
        plan = Plan(
            id=str(uuid.uuid4()),
            code="equipe",
            name="Equipe",
            price_cents=4900,
            currency="BRL",
            seat_limit=15,
            overage_cents_per_seat=4900,
            trial_days=14,
            active=True,
        )
        db.add(plan)
        db.flush()
        db.add(
            Subscription(
                organization_id=seeded["main_org_id"],
                plan_id=plan.id,
                status="trialing",
                seats_purchased=3,
                trial_ends_at=None,
                current_period_end=None,
            )
        )
        db.commit()

    body, _ = _get_context(client, login(client, EMAILS[0]))

    assert body["subscription"] == {
        "plan_code": "equipe",
        "plan_name": "Equipe",
        "status": "trialing",
        "seats_purchased": 3,
        "seat_limit": 15,
        "trial_ends_at": None,
        "current_period_end": None,
        "price_cents": 4900,
        "overage_cents_per_seat": 4900,
        "provider": "stub",
    }
    assert body["workspace_inicial_id"] == seeded["main_id"]
    assert body["equipe_inicial_id"] == body["workspaces"][0]["teams"][0]["id"]
    assert body["organizacao"] == body["active_organization"]
    assert body["seats"] == {"plan_code": "equipe", "limit": 15, "used": 5}


def test_billing_manage_requires_owner_or_billing_owner(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, object]
) -> None:
    headers = login(client, EMAILS[1])
    before, _ = _get_context(client, headers)
    assert before["capabilities"]["billing"] == {"view": True, "manage": False}

    with session_factory() as db:
        member = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == seeded["main_org_id"],
                OrganizationMember.user_id == seeded["users"][EMAILS[1]].id,
            )
        )
        assert member is not None
        member.role = "billing_owner"
        db.commit()

    after, _ = _get_context(client, headers)
    assert after["capabilities"]["billing"] == {"view": True, "manage": True}


def test_user_response_exposes_name_and_title_additively(
    client: TestClient, seeded: dict[str, object]
) -> None:
    response = client.get("/auth/me", headers=login(client, EMAILS[0]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Owner Ressonant"
    assert body["title"] == "Dono da Empresa"
    assert body["cpf"] == seeded["users"][EMAILS[0]].cpf


def test_atomic_registration_bootstrap_exposes_initial_ids_and_seats(
    client: TestClient,
) -> None:
    payload = {
        "email": "bootstrap.owner@ressonant.dev",
        "senha": "senhaSegura123",
        "telefone": "11987654321",
        "cpf": "52998224725",
        "idade": 30,
        "termos_contrato": True,
        "nome_completo": "Bootstrap Owner",
        "cargo": "Fundador",
        "organizacao": {
            "nome": "Org Bootstrap",
            "slug": "org-bootstrap",
            "corporate_domain": "example.com",
        },
        "plano_id": "inicial",
        "trial": True,
        "workspace_nome": "Workspace Bootstrap",
        "equipe_inicial_nome": "Equipe Bootstrap",
        "convidados": [],
    }
    reg = client.post("/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    reg_body = reg.json()

    token = client.post("/auth/login", json={"email": payload["email"], "senha": payload["senha"]})
    assert token.status_code == 200, token.text
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    body, seen = _get_context(client, headers)
    assert body["workspace_inicial_id"] == reg_body["workspace_inicial_id"]
    assert body["equipe_inicial_id"] == reg_body["equipe_inicial_id"]
    assert body["organizacao"]["id"] == reg_body["organizacao"]["id"]
    assert body["organizacao"]["id"] == body["active_organization"]["id"]
    assert body["seats"]["plan_code"] == reg_body["seats"]["plan_code"]
    assert body["seats"]["used"] >= 1
    assert body["seats"]["limit"] == reg_body["seats"]["limit"]
    assert body["seats"] == reg_body["seats"]
    assert not [path for path in seen if path in {"/auth/me"}]


def test_context_route_is_authenticated_and_published_without_query_parameters(
    client: TestClient,
) -> None:
    assert client.get("/me/context").status_code == 401

    operation = app.openapi()["paths"]["/me/context"]["get"]
    assert operation["tags"] == ["context"]
    assert operation.get("parameters") is None
    assert operation["security"] == [{"HTTPBearer": []}]
    schema = app.openapi()["components"]["schemas"]["MeContextResponse"]
    assert set(schema["required"]) == {
        "user",
        "organizations",
        "active_organization",
        "workspaces",
        "capabilities",
        "subscription",
        "permission_version",
        "workspace_inicial_id",
        "equipe_inicial_id",
        "organizacao",
        "seats",
    }
    workspace = app.openapi()["components"]["schemas"]["WorkspaceContextResponse"]
    assert set(workspace["required"]) == {
        "id",
        "name",
        "slug",
        "organization_id",
        "role",
        "member_ids",
        "teams",
        "capabilities",
        "permission_version",
    }
