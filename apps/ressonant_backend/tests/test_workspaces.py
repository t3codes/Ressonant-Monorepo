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


def test_create_workspace_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/workspaces",
        json={"name": "Plataforma", "slug": "plataforma"},
    )
    assert response.status_code == 401


def test_create_workspace_success(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces",
        json={"name": "Plataforma", "slug": "plataforma", "description": "Time de plataforma"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Plataforma"
    assert body["slug"] == "plataforma"
    assert body["owner_id"] is not None
    assert "senha_hash" not in body


def test_create_workspace_duplicate_slug(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    client.post("/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers)
    response = client.post(
        "/workspaces", json={"name": "Outro", "slug": "plataforma"}, headers=headers
    )
    assert response.status_code == 409, response.text


def test_create_workspace_invalid_slug(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.post("/workspaces", json={"name": "X", "slug": "ab"}, headers=headers)
    assert response.status_code == 422, response.text


def test_list_workspaces_requires_auth(client: TestClient) -> None:
    assert client.get("/workspaces").status_code == 401


def test_list_workspaces_empty(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get("/workspaces", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_workspaces_pagination(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    for i in range(3):
        client.post(
            "/workspaces",
            json={"name": f"WS {i}", "slug": f"ws-{i}"},
            headers=headers,
        )

    response = client.get("/workspaces?skip=1&limit=1", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["skip"] == 1
    assert body["limit"] == 1


def test_get_workspace_member(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    ).json()

    # Ana é owner → pode ver
    response = client.get(f"/workspaces/{created['id']}", headers=headers)
    assert response.status_code == 200, response.text

    # Bia não é membro → 403
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.get(f"/workspaces/{created['id']}", headers=headers_bia)
    assert response.status_code == 403, response.text


def test_get_workspace_not_found(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get("/workspaces/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404, response.text


def test_get_workspace_invalid_id(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    response = client.get("/workspaces/nao-e-um-uuid", headers=headers)
    assert response.status_code == 404, response.text


def test_update_workspace_owner(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    ).json()

    response = client.put(
        f"/workspaces/{created['id']}",
        json={"name": "Plataforma Atualizada"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Plataforma Atualizada"
    assert response.json()["slug"] == "plataforma"  # slug não muda


def test_update_workspace_non_member(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    ).json()

    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.put(
        f"/workspaces/{created['id']}",
        json={"name": "Hack"},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text


def test_deactivate_workspace_only_owner(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    ).json()

    # Bia não é owner → 403
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.patch(
        f"/workspaces/{created['id']}/status",
        json={"status_ativo": False},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text

    # Ana é owner → 200
    response = client.patch(
        f"/workspaces/{created['id']}/status",
        json={"status_ativo": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status_ativo"] is False


def test_add_member_only_owner_or_admin(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf="52998224725")
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    carol = make_user(session_factory, email="carol@ressonant.dev", cpf="39053344705")
    headers = _headers(client, "ana@ressonant.dev")

    created = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    ).json()

    # Bia não é membro admin → 403 ao tentar adicionar Carol
    headers_bia = _headers(client, "bia@ressonant.dev")
    response = client.post(
        f"/workspaces/{created['id']}/members",
        json={"user_id": carol.id},
        headers=headers_bia,
    )
    assert response.status_code == 403, response.text
