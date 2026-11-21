from app.modules.organization.domain.models import Organization, OrganizationMember
from fastapi.testclient import TestClient
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
