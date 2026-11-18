from fastapi.testclient import TestClient

from tests.conftest import login, make_user, register_payload


def _create_workspace_and_team(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    headers = login(client, email)
    ws = client.post("/workspaces", json={"name": "WS", "slug": "ws"}, headers=headers).json()
    team = client.post("/teams", json={"name": "Team", "slug": "team", "workspace_id": ws["id"]}, headers=headers).json()
    return ws, team, headers


def test_create_board_requires_auth(client):
    assert client.post("/boards", json={"name": "B", "slug": "b", "workspace_id": "x", "team_id": "y"}).status_code == 401


def test_create_board_success(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    r = client.post("/boards", json={"name": "Board 1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Board 1"
    assert body["slug"] == "board-1"
    assert body["team_id"] == team["id"]


def test_create_board_duplicate_slug(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers)
    r = client.post("/boards", json={"name": "B2", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers)
    assert r.status_code == 409, r.text


def test_list_boards(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers)
    r = client.get(f"/boards?workspace_id={ws['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1


def test_get_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    r = client.get(f"/boards/{b['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_update_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    r = client.put(f"/boards/{b['id']}", json={"name": "Board 1 Atualizado"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Board 1 Atualizado"


def test_deactivate_board(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    r = client.patch(f"/boards/{b['id']}/status", json={"status_ativo": False}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status_ativo"] is False


def test_list_board_columns(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    r = client.get(f"/boards/{b['id']}/columns", headers=headers)
    assert r.status_code == 200, r.text
    # Deve ter as 3 colunas padrão criadas automaticamente
    assert len(r.json()["items"]) == 3


def test_create_board_column(client, session_factory):
    ws, team, headers = _create_workspace_and_team(client, session_factory)
    b = client.post("/boards", json={"name": "B1", "slug": "board-1", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    r = client.post(f"/boards/{b['id']}/columns", json={"name": "Review", "slug": "review", "position": 3}, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Review"
