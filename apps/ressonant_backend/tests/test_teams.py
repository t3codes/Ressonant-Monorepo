from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team
from app.modules.teams.usecases.services import derive_key_prefix
from app.modules.workspace.domain.models import Workspace
from app.modules.workspace_management.domain.models import WorkspaceCapabilityGrant
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user


def make_user(session_factory, **kwargs):
    """Usuário de teste com organização elegível (regra real de criação de workspace)."""
    user = _plain_make_user(session_factory, **kwargs)
    with session_factory() as db:
        organization = Organization(name=f"Org {user.id}", slug=f"org-{user.id}")
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    return login(client, email)


def _add_workspace_member(
    client: TestClient, workspace_id: str, owner_email: str, user_id: str, role: str = "member"
) -> None:
    response = client.post(
        f"/workspaces/{workspace_id}/members",
        json={"user_id": user_id, "role": role},
        headers=_headers(client, owner_email),
    )
    assert response.status_code == 201, response.text


def _create_workspace(
    client: TestClient, session_factory, email: str, name: str, slug: str
) -> dict:
    make_user(session_factory, email=email, cpf="52998224725")
    headers = _headers(client, email)
    response = client.post(
        "/workspaces",
        json={"name": name, "slug": slug},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _set_capability_effect(
    session_factory,
    workspace_id: str,
    user_id: str,
    capability: str,
    effect: str,
) -> None:
    with session_factory() as db:
        # Limpeza explícita: nenhum override residual pode decidir o resultado do teste.
        previous = db.scalars(
            select(WorkspaceCapabilityGrant).where(
                WorkspaceCapabilityGrant.workspace_id == workspace_id,
                WorkspaceCapabilityGrant.user_id == user_id,
                WorkspaceCapabilityGrant.capability == capability,
            )
        ).all()
        for grant in previous:
            db.delete(grant)
        granted_by_id = db.scalar(select(Workspace.owner_id).where(Workspace.id == workspace_id))
        assert granted_by_id is not None
        db.add(
            WorkspaceCapabilityGrant(
                workspace_id=workspace_id,
                user_id=user_id,
                capability=capability,
                effect=effect,
                granted_by_id=granted_by_id,
            )
        )
        db.commit()


def test_create_team_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/teams",
        json={
            "name": "Time A",
            "slug": "time-a",
            "workspace_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 401


def test_create_team_success(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    response = client.post(
        "/teams",
        json={
            "name": "Time A",
            "slug": "time-a",
            "workspace_id": workspace["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Time A"
    assert body["slug"] == "time-a"
    assert body["workspace_id"] == workspace["id"]
    assert body["owner_id"] is not None


def test_create_team_duplicate_slug(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    )
    response = client.post(
        "/teams",
        json={"name": "Time B", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    )
    assert response.status_code == 409, response.text


def test_create_team_invalid_slug(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    response = client.post(
        "/teams",
        json={"name": "X", "slug": "ab", "workspace_id": workspace["id"]},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_create_team_not_member_of_workspace(client: TestClient, session_factory) -> None:
    # Ana cria workspace
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers_ana = _headers(client, "ana@ressonant.dev")
    workspace = client.post(
        "/workspaces",
        json={"name": "Plataforma", "slug": "plataforma"},
        headers=headers_ana,
    ).json()

    # Bia tenta criar team no workspace de Ana (não é membro)
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers_bia = _headers(client, "bia@ressonant.dev")

    response = client.post(
        "/teams",
        json={"name": "Time B", "slug": "time-b", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text


def test_list_teams_requires_auth(client: TestClient) -> None:
    assert client.get("/teams").status_code == 401


def test_list_teams_empty(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get(f"/teams?workspace_id={workspace['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_teams_pagination(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    for i in range(3):
        client.post(
            "/teams",
            json={"name": f"Time {i}", "slug": f"time-{i}", "workspace_id": workspace["id"]},
            headers=headers,
        )

    response = client.get(
        f"/teams?workspace_id={workspace['id']}&skip=1&limit=1",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["skip"] == 1
    assert body["limit"] == 1


def test_get_team_member(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()

    # Ana é owner → pode ver
    response = client.get(f"/teams/{created['id']}", headers=headers)
    assert response.status_code == 200, response.text

    # Bia não é membro → 403
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.get(f"/teams/{created['id']}", headers=headers_bia)
    assert response.status_code == 403, response.text


def test_get_team_not_found(client: TestClient, session_factory) -> None:
    _create_workspace(client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get("/teams/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404, response.text


def test_get_team_invalid_id(client: TestClient, session_factory) -> None:
    _create_workspace(client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get("/teams/nao-e-um-uuid", headers=headers)
    assert response.status_code == 404, response.text


def test_update_team_owner(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()

    response = client.put(
        f"/teams/{created['id']}",
        json={"name": "Time A Atualizado"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Time A Atualizado"
    assert response.json()["slug"] == "time-a"  # slug não muda


def test_update_team_non_member(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()

    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.put(
        f"/teams/{created['id']}",
        json={"name": "Hack"},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text


def test_workspace_owner_outside_team_can_get_update_and_list_members(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=_headers(client, "bia@ressonant.dev"),
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    headers_ana = _headers(client, "ana@ressonant.dev")

    response = client.get(f"/teams/{team_id}", headers=headers_ana)
    assert response.status_code == 200, response.text
    response = client.get(f"/teams/{team_id}/members", headers=headers_ana)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1

    response = client.put(
        f"/teams/{team_id}", json={"name": "Time A Renomeado"}, headers=headers_ana
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Time A Renomeado"


def test_workspace_admin_outside_team_can_get_update_but_not_change_status(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    carol = make_user(session_factory, email="carol@ressonant.dev", cpf="39053344705")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", carol.id, role="admin")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=_headers(client, "bia@ressonant.dev"),
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    headers_carol = _headers(client, "carol@ressonant.dev")

    assert client.get(f"/teams/{team_id}", headers=headers_carol).status_code == 200
    assert client.get(f"/teams/{team_id}/members", headers=headers_carol).status_code == 200
    response = client.put(
        f"/teams/{team_id}", json={"name": "Time A Renomeado"}, headers=headers_carol
    )
    assert response.status_code == 200, response.text
    response = client.put(f"/teams/{team_id}", json={"status_ativo": False}, headers=headers_carol)
    assert response.status_code == 403, response.text


def test_team_admin_cannot_change_status_via_put(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    headers_ana = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_ana,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    added = client.post(
        f"/teams/{team_id}/members",
        json={"user_id": bia.id, "role": "admin"},
        headers=headers_ana,
    )
    assert added.status_code == 201, added.text
    headers_bia = _headers(client, "bia@ressonant.dev")

    response = client.put(
        f"/teams/{team_id}",
        json={"name": "Hack", "status_ativo": False},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"

    team = client.get(f"/teams/{team_id}", headers=headers_ana).json()
    assert team["name"] == "Time A"
    assert team["status_ativo"] is True

    response = client.put(f"/teams/{team_id}", json={"name": "Time A Admin"}, headers=headers_bia)
    assert response.status_code == 200, response.text


def test_regular_team_member_cannot_update_team(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    headers_ana = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_ana,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    added = client.post(
        f"/teams/{team_id}/members",
        json={"user_id": bia.id, "role": "member"},
        headers=headers_ana,
    )
    assert added.status_code == 201, added.text

    response = client.put(
        f"/teams/{team_id}", json={"name": "Hack"}, headers=_headers(client, "bia@ressonant.dev")
    )
    assert response.status_code == 403, response.text


def test_interno_admin_outside_team_can_get_update_and_list_members(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    admin = make_user(session_factory, email="admin@ressonant.dev", cpf="16899535009", admin=True)
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=_headers(client, "bia@ressonant.dev"),
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    assert admin.id is not None
    headers_admin = _headers(client, "admin@ressonant.dev")

    assert client.get(f"/teams/{team_id}", headers=headers_admin).status_code == 200
    assert client.get(f"/teams/{team_id}/members", headers=headers_admin).status_code == 200
    response = client.put(
        f"/teams/{team_id}", json={"name": "Time A Renomeado"}, headers=headers_admin
    )
    assert response.status_code == 200, response.text


def test_deleted_team_stays_hidden_from_owner_and_admin(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    make_user(session_factory, email="admin@ressonant.dev", cpf="16899535009", admin=True)
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=_headers(client, "bia@ressonant.dev"),
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    with session_factory() as db:
        team = db.scalar(select(Team).where(Team.id == team_id))
        assert team is not None
        team.is_deleted = True
        db.commit()

    headers = {
        "ana": _headers(client, "ana@ressonant.dev"),
        "admin": _headers(client, "admin@ressonant.dev"),
    }
    for actor_headers in headers.values():
        assert client.get(f"/teams/{team_id}", headers=actor_headers).status_code == 404
        assert client.get(f"/teams/{team_id}/members", headers=actor_headers).status_code == 404
        response = client.put(f"/teams/{team_id}", json={"name": "Hack"}, headers=actor_headers)
        assert response.status_code == 404, response.text


def test_deactivate_team_only_owner(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()

    # Bia não é owner → 403
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.patch(
        f"/teams/{created['id']}/status",
        json={"status_ativo": False},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text

    # Ana é owner → 200
    response = client.patch(
        f"/teams/{created['id']}/status",
        json={"status_ativo": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status_ativo"] is False


def test_add_team_member_only_owner_or_admin(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    carol = make_user(session_factory, email="carol@ressonant.dev", cpf="39053344705")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()

    # Bia não é membro admin → 403 ao tentar adicionar Carol
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.post(
        f"/teams/{created['id']}/members",
        json={"user_id": carol.id},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text


def test_derive_key_prefix_normalizes_slug_with_hyphen() -> None:
    assert derive_key_prefix("time-de-plataforma") == "TIMEDEPLATAFORMA"


def test_derive_key_prefix_falls_back_for_special_characters() -> None:
    assert derive_key_prefix("###") == "TEAM"


def test_derive_key_prefix_truncates_to_20_chars() -> None:
    derived = derive_key_prefix("abcdefghijklmnopqrstuvwxyz")
    assert derived == "ABCDEFGHIJKLMNOPQRST"
    assert len(derived) == 20


def test_create_team_persists_derived_key_prefix(
    client: TestClient, session_factory, monkeypatch
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")

    seen_at_add: list[str | None] = []
    original_add = TeamRepository.add

    def capture_key_prefix(repository: TeamRepository, team: Team) -> Team:
        # Antes do flush: prova que o service preencheu, não o listener do conftest.
        seen_at_add.append(team.key_prefix)
        return original_add(repository, team)

    monkeypatch.setattr(TeamRepository, "add", capture_key_prefix)

    response = client.post(
        "/teams",
        json={
            "name": "Time Frontend",
            "slug": "frontend-plataforma",
            "workspace_id": workspace["id"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    team_id = response.json()["id"]
    assert seen_at_add == ["FRONTENDPLATAFORMA"]

    with session_factory() as db:
        persisted = db.scalar(select(Team.key_prefix).where(Team.id == team_id))
    assert persisted == "FRONTENDPLATAFORMA"


def test_key_prefix_collision_same_workspace_gets_numeric_suffix(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")
    slugs = ("team-a", "team.a")  # ambos normalizam para TEAMA
    team_ids: list[str] = []

    for slug in slugs:
        response = client.post(
            "/teams",
            json={"name": f"Time {slug}", "slug": slug, "workspace_id": workspace["id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        team_ids.append(response.json()["id"])

    with session_factory() as db:
        prefixes = [
            db.scalar(select(Team.key_prefix).where(Team.id == team_id)) for team_id in team_ids
        ]
    assert prefixes == ["TEAMA", "TEAMA2"]


def test_key_prefix_scoped_to_workspace(client: TestClient, session_factory) -> None:
    workspace_a = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")
    response = client.post(
        "/workspaces",
        json={"name": "Plataforma B", "slug": "plataforma-b"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    workspace_b = response.json()
    slugs = ("team-a", "team.a")  # mesmo prefixo normalizado em workspaces distintos
    team_ids: list[str] = []

    for workspace, slug in ((workspace_a, slugs[0]), (workspace_b, slugs[1])):
        response = client.post(
            "/teams",
            json={"name": f"Time {slug}", "slug": slug, "workspace_id": workspace["id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        team_ids.append(response.json()["id"])

    with session_factory() as db:
        prefixes = [
            db.scalar(select(Team.key_prefix).where(Team.id == team_id)) for team_id in team_ids
        ]
    assert prefixes == ["TEAMA", "TEAMA"]


def test_key_prefix_collision_on_long_base_stays_within_20_chars(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")
    slugs = ("abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrstuvwxyz-2")
    team_ids: list[str] = []

    for slug in slugs:
        response = client.post(
            "/teams",
            json={"name": f"Time {slug}", "slug": slug, "workspace_id": workspace["id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        team_ids.append(response.json()["id"])

    with session_factory() as db:
        prefixes = [
            db.scalar(select(Team.key_prefix).where(Team.id == team_id)) for team_id in team_ids
        ]
    assert prefixes == ["ABCDEFGHIJKLMNOPQRST", "ABCDEFGHIJKLMNOPQRS2"]
    assert all(len(prefix) <= 20 for prefix in prefixes)


def test_key_prefix_race_becomes_conflict_error(
    client: TestClient, session_factory, monkeypatch
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    headers = _headers(client, "ana@ressonant.dev")
    slug = "team-race"

    def raise_unique_violation(repository: TeamRepository, team: Team) -> Team:
        raise IntegrityError(
            "INSERT INTO teams",
            {"workspace_id": team.workspace_id, "key_prefix": team.key_prefix},
            Exception("uq_teams_workspace_key_prefix"),
        )

    monkeypatch.setattr(TeamRepository, "add", raise_unique_violation)
    response = client.post(
        "/teams",
        json={"name": "Time Race", "slug": slug, "workspace_id": workspace["id"]},
        headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "TEAM_KEY_PREFIX_CONFLICT"

    with session_factory() as db:
        assert db.scalar(select(Team.id).where(Team.slug == slug)) is None


def test_deny_teams_create_blocks_authorized_workspace_member(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    headers_bia = _headers(client, "bia@ressonant.dev")

    # Bia é membro do workspace: já tem autorização positiva para criar times.
    first = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert first.status_code == 201, first.text

    _set_capability_effect(session_factory, workspace["id"], bia.id, "teams_create", "deny")
    response = client.post(
        "/teams",
        json={"name": "Time B", "slug": "time-b", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "CAPABILITY_DENIED"

    # A listagem é escopada a teams dos quais o chamador é membro: Bia é a autora do team.
    listed = client.get(f"/teams?workspace_id={workspace['id']}", headers=headers_bia)
    assert listed.json()["total"] == 1, listed.text
    with session_factory() as db:
        slugs = db.scalars(select(Team.slug).where(Team.workspace_id == workspace["id"])).all()
    assert list(slugs) == ["time-a"]


def test_deny_teams_create_does_not_veto_inherent_actors(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    with session_factory() as db:
        owner_id = db.scalar(select(Workspace.owner_id).where(Workspace.id == workspace["id"]))
    assert owner_id is not None
    admin = make_user(session_factory, email="admin@ressonant.dev", cpf="16899535009", admin=True)
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", admin.id)

    # Dono do workspace e interno_adm: deny órfão no banco não pode gerar auto-negação.
    for email, user_id in (("ana@ressonant.dev", owner_id), ("admin@ressonant.dev", admin.id)):
        _set_capability_effect(session_factory, workspace["id"], user_id, "teams_create", "deny")
        response = client.post(
            "/teams",
            json={
                "name": f"Time {email.split('@')[0]}",
                "slug": f"time-{email.split('@')[0]}",
                "workspace_id": workspace["id"],
            },
            headers=_headers(client, email),
        )
        assert response.status_code == 201, response.text

    with session_factory() as db:
        slugs = db.scalars(select(Team.slug).where(Team.workspace_id == workspace["id"])).all()
    assert sorted(slugs) == ["time-admin", "time-ana"]


def test_deny_teams_update_blocks_name_and_description(client: TestClient, session_factory) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    headers_bia = _headers(client, "bia@ressonant.dev")
    headers_ana = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    allowed = client.put(
        f"/teams/{team_id}",
        json={"name": "Time A Editado", "description": "Descrição original"},
        headers=headers_bia,
    )
    assert allowed.status_code == 200, allowed.text

    _set_capability_effect(session_factory, workspace["id"], bia.id, "teams_update", "deny")
    response = client.put(
        f"/teams/{team_id}",
        json={"name": "Hack", "description": "Descrição alterada"},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "CAPABILITY_DENIED"

    persisted = client.get(f"/teams/{team_id}", headers=headers_ana)
    assert persisted.json()["name"] == "Time A Editado"
    assert persisted.json()["description"] == "Descrição original"


def test_deny_members_manage_blocks_add_and_update_member(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    carol = make_user(session_factory, email="carol@ressonant.dev", cpf="39053344705")
    dani = make_user(session_factory, email="dani@ressonant.dev", cpf="16899535009")
    for target in (bia, carol, dani):
        _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", target.id)

    headers_bia = _headers(client, "bia@ressonant.dev")
    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    added = client.post(
        f"/teams/{team_id}/members", json={"user_id": carol.id}, headers=headers_bia
    )
    assert added.status_code == 201, added.text

    _set_capability_effect(session_factory, workspace["id"], bia.id, "members_manage", "deny")
    add_response = client.post(
        f"/teams/{team_id}/members", json={"user_id": dani.id}, headers=headers_bia
    )
    assert add_response.status_code == 403, add_response.text
    assert add_response.json()["error_code"] == "CAPABILITY_DENIED"

    update_response = client.patch(
        f"/teams/{team_id}/members/{carol.id}", json={"role": "admin"}, headers=headers_bia
    )
    assert update_response.status_code == 403, update_response.text
    assert update_response.json()["error_code"] == "CAPABILITY_DENIED"

    members = client.get(
        f"/teams/{team_id}/members", headers=_headers(client, "ana@ressonant.dev")
    ).json()
    assert members["total"] == 2
    roles = {item["user_id"]: item["role"] for item in members["items"]}
    assert roles == {bia.id: "admin", carol.id: "member"}


def test_allow_teams_create_does_not_grant_access_to_outsider(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _set_capability_effect(session_factory, workspace["id"], bia.id, "teams_create", "allow")

    response = client.post(
        "/teams",
        json={"name": "Time B", "slug": "time-b", "workspace_id": workspace["id"]},
        headers=_headers(client, "bia@ressonant.dev"),
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"


def test_allow_teams_update_does_not_grant_access_to_plain_member(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=_headers(client, "ana@ressonant.dev"),
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    _set_capability_effect(session_factory, workspace["id"], bia.id, "teams_update", "allow")

    response = client.put(
        f"/teams/{team_id}", json={"name": "Hack"}, headers=_headers(client, "bia@ressonant.dev")
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"
    persisted = client.get(
        f"/teams/{team_id}", headers=_headers(client, "ana@ressonant.dev")
    ).json()
    assert persisted["name"] == "Time A"


def test_soft_delete_stays_owner_only_and_deleted_team_returns_404_with_deny(
    client: TestClient, session_factory
) -> None:
    workspace = _create_workspace(
        client, session_factory, "ana@ressonant.dev", "Plataforma", "plataforma"
    )
    bia = make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    _add_workspace_member(client, workspace["id"], "ana@ressonant.dev", bia.id)
    headers_bia = _headers(client, "bia@ressonant.dev")

    created = client.post(
        "/teams",
        json={"name": "Time A", "slug": "time-a", "workspace_id": workspace["id"]},
        headers=headers_bia,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    _set_capability_effect(session_factory, workspace["id"], bia.id, "teams_soft_delete", "deny")

    response = client.post(f"/teams/{team_id}/soft-delete", json={}, headers=headers_bia)
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"

    with session_factory() as db:
        team = db.scalar(select(Team).where(Team.id == team_id))
        assert team is not None
        team.is_deleted = True
        db.commit()

    assert client.get(f"/teams/{team_id}", headers=headers_bia).status_code == 404
    response = client.put(f"/teams/{team_id}", json={"name": "Hack"}, headers=headers_bia)
    assert response.status_code == 404, response.text
    assert client.get(f"/teams/{team_id}/members", headers=headers_bia).status_code == 404
