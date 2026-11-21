from app.modules.organization.domain.models import Organization, OrganizationMember
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


def _create_workspace_and_team(
    client, session_factory, email="ana@ressonant.dev", cpf="52998224725"
):
    make_user(session_factory, email=email, cpf=cpf)
    headers = login(client, email)
    ws = client.post(
        "/workspaces", json={"name": "Workspace Teste", "slug": "workspace-teste"}, headers=headers
    ).json()
    team = client.post(
        "/teams",
        json={"name": "Time Teste", "slug": "time-teste", "workspace_id": ws["id"]},
        headers=headers,
    ).json()
    return ws, team, headers


def test_create_board_requires_auth(client):
    assert (
        client.post(
            "/boards",
            json={
                "name": "Board Teste",
                "slug": "board-teste",
                "workspace_id": "x",
                "team_id": "y",
            },
        ).status_code
        == 401
    )


def test_create_board_success(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    r = client.post(
        "/boards",
        json={
            "name": "Board Teste",
            "slug": "board-teste",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Board Teste"
    assert body["slug"] == "board-teste"
    assert body["team_id"] == team["id"]


def test_create_board_duplicate_slug(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    )
    r = client.post(
        "/boards",
        json={
            "name": "Board 2",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    )
    assert r.status_code == 409, r.text


def test_list_boards(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    )
    r = client.get(f"/boards?workspace_id={ws['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1


def test_get_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    r = client.get(f"/boards/{b['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_update_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    r = client.put(f"/boards/{b['id']}", json={"name": "Board 1 Atualizado"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Board 1 Atualizado"


def test_deactivate_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    r = client.patch(f"/boards/{b['id']}/status", json={"status_ativo": False}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status_ativo"] is False


def test_list_board_columns(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    r = client.get(f"/boards/{b['id']}/columns", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 3


def test_create_board_column(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    r = client.post(
        f"/boards/{b['id']}/columns",
        json={"name": "Revisao", "slug": "revisao", "position": 3},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Revisao"
