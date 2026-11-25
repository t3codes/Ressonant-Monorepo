from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.workspace_management.domain.models import WorkspaceCapabilityGrant
from app.user.models import User
from sqlalchemy import select
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


def _user_id_by_email(session_factory, email):
    with session_factory() as db:
        return db.scalar(select(User.id).where(User.email == email))


def _set_capability(session_factory, workspace_id, user_id, capability, effect, granted_by_id):
    with session_factory() as db:
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


def _create_board_for_capability_tests(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    board = client.post(
        "/boards",
        json={
            "name": "Board 1",
            "slug": "board-1",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    return ws, board, headers


def test_columns_manage_deny_blocks_column_mutations(client, session_factory):
    ws, board, owner_headers = _create_board_for_capability_tests(client, session_factory)
    owner_id = _user_id_by_email(session_factory, "ana@ressonant.dev")
    make_user(session_factory, email="bia@ressonant.dev", cpf="11144477735")
    user_id = _user_id_by_email(session_factory, "bia@ressonant.dev")
    ws_member = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"user_id": user_id, "role": "member"},
        headers=owner_headers,
    )
    assert ws_member.status_code == 201, ws_member.text
    added = client.post(
        f"/teams/{board['team_id']}/members",
        json={"user_id": user_id, "role": "admin"},
        headers=owner_headers,
    )
    assert added.status_code == 201, added.text
    headers = login(client, "bia@ressonant.dev")
    _set_capability(session_factory, ws["id"], user_id, "columns_manage", "deny", owner_id)

    columns = client.get(f"/boards/{board['id']}/columns", headers=headers).json()["items"]
    assert len(columns) == 3
    column_id = columns[0]["id"]

    create = client.post(
        f"/boards/{board['id']}/columns",
        json={"name": "Revisao", "slug": "revisao", "position": 3},
        headers=headers,
    )
    assert create.status_code == 403, create.text
    assert create.json()["error_code"] == "FORBIDDEN"

    update = client.patch(
        f"/boards/{board['id']}/columns/{column_id}",
        json={"name": "Backlog alterado"},
        headers=headers,
    )
    assert update.status_code == 403, update.text

    delete = client.delete(f"/boards/{board['id']}/columns/{column_id}", headers=headers)
    assert delete.status_code == 403, delete.text

    reorder = client.patch(
        f"/boards/{board['id']}/columns/reorder",
        json={"ordered_column_ids": [c["id"] for c in reversed(columns)]},
        headers=headers,
    )
    assert reorder.status_code == 403, reorder.text

    after = client.get(f"/boards/{board['id']}/columns", headers=headers).json()["items"]
    assert [c["id"] for c in after] == [c["id"] for c in columns]
    assert after[0]["name"] == columns[0]["name"]


def test_columns_manage_deny_does_not_veto_inherent_actors(client, session_factory):
    ws, board, owner_headers = _create_board_for_capability_tests(client, session_factory)
    owner_id = _user_id_by_email(session_factory, "ana@ressonant.dev")
    make_user(session_factory, email="admin@ressonant.dev", cpf="16899535009", admin=True)
    admin_id = _user_id_by_email(session_factory, "admin@ressonant.dev")
    ws_member = client.post(
        f"/workspaces/{ws['id']}/members",
        json={"user_id": admin_id, "role": "member"},
        headers=owner_headers,
    )
    assert ws_member.status_code == 201, ws_member.text
    added = client.post(
        f"/teams/{board['team_id']}/members",
        json={"user_id": admin_id, "role": "admin"},
        headers=owner_headers,
    )
    assert added.status_code == 201, added.text
    admin_headers = login(client, "admin@ressonant.dev")

    # Dono do workspace e interno_adm: deny órfão não bloqueia regra dura.
    for email, user_id, headers in (
        ("ana@ressonant.dev", owner_id, owner_headers),
        ("admin@ressonant.dev", admin_id, admin_headers),
    ):
        _set_capability(session_factory, ws["id"], user_id, "columns_manage", "deny", owner_id)
        response = client.post(
            f"/boards/{board['id']}/columns",
            json={
                "name": f"Revisao {email.split('@')[0]}",
                "slug": f"revisao-{email.split('@')[0]}",
                "position": 3,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["name"] == f"Revisao {email.split('@')[0]}"


def test_columns_manage_allow_does_not_grant_outsider(client, session_factory):
    ws, board, _ = _create_board_for_capability_tests(client, session_factory)
    make_user(session_factory, email="outsider@ressonant.dev", cpf="11144477735")
    outsider_id = _user_id_by_email(session_factory, "outsider@ressonant.dev")
    owner_id = _user_id_by_email(session_factory, "ana@ressonant.dev")
    _set_capability(session_factory, ws["id"], outsider_id, "columns_manage", "allow", owner_id)

    outsider_headers = login(client, "outsider@ressonant.dev")
    response = client.post(
        f"/boards/{board['id']}/columns",
        json={"name": "Revisao", "slug": "revisao", "position": 3},
        headers=outsider_headers,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"
    assert "não é membro do time" in response.json()["message"]
