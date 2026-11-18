from fastapi.testclient import TestClient

from tests.conftest import login, make_user, register_payload


def _create_board(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    headers = login(client, email)
    ws = client.post("/workspaces", json={"name": "WS", "slug": "ws"}, headers=headers).json()
    team = client.post("/teams", json={"name": "Team", "slug": "team", "workspace_id": ws["id"]}, headers=headers).json()
    board = client.post("/boards", json={"name": "Board", "slug": "board", "workspace_id": ws["id"], "team_id": team["id"]}, headers=headers).json()
    return board, headers


def test_create_card_requires_auth(client):
    assert client.post("/cards", json={"title": "T", "board_id": "x", "team_id": "y"}).status_code == 401


def test_create_card_success(client, session_factory):
    board, headers = _create_board(client, session_factory)
    r = client.post("/cards", json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Card 1"
    assert body["board_id"] == board["id"]
    assert body["column_id"] is None  # Nasce no backlog


def test_list_cards(client, session_factory):
    board, headers = _create_board(client, session_factory)
    client.post("/cards", json={"title": "C1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers)
    r = client.get(f"/cards?board_id={board['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1


def test_get_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post("/cards", json={"title": "C1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers).json()
    r = client.get(f"/cards/{c['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_update_card_with_version(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post("/cards", json={"title": "C1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers).json()
    r = client.put(f"/cards/{c['id']}", json={"title": "C1 Atualizado", "expected_version": c["version"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "C1 Atualizado"


def test_move_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post("/cards", json={"title": "C1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers).json()
    # Criar uma coluna para mover
    col = client.post(f"/boards/{board['id']}/columns", json={"name": "Doing", "slug": "doing", "position": 1}, headers=headers).json()
    r = client.post(f"/cards/{c['id']}/move", json={"column_id": col["id"], "expected_version": c["version"]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["column_id"] == col["id"]


def test_clone_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post("/cards", json={"title": "C1", "board_id": board["id"], "team_id": board["team_id"]}, headers=headers).json()
    r = client.post(f"/cards/{c['id']}/clone", headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Cópia de C1"
    assert r.json()["id"] != c["id"]
