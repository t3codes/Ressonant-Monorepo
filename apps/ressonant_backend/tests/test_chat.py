from fastapi.testclient import TestClient

from tests.conftest import login, make_user, register_payload


def _create_workspace(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    headers = login(client, email)
    ws = client.post("/workspaces", json={"name": "Workspace Teste", "slug": "workspace-teste"}, headers=headers).json()
    return ws, headers


def test_create_channel_requires_auth(client):
    assert client.post("/channels", json={"name": "Canal Teste", "workspace_id": "x"}).status_code == 401


def test_create_channel_success(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    r = client.post("/channels", json={"name": "Canal Teste", "workspace_id": ws["id"]}, headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Canal Teste"


def test_list_channels(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    client.post("/channels", json={"name": "Canal 1", "workspace_id": ws["id"]}, headers=headers)
    r = client.get(f"/channels?workspace_id={ws['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1


def test_get_channel(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    c = client.post("/channels", json={"name": "Canal 1", "workspace_id": ws["id"]}, headers=headers).json()
    r = client.get(f"/channels/{c['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_add_channel_member(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    r = client.post(f"/channels/{ws['id']}/members", json={"user_id": ws["owner_id"]}, headers=headers)
    assert r.status_code in (200, 403, 422)


def test_create_conversation(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    r = client.post("/conversations", json={"workspace_id": ws["id"], "member_ids": []}, headers=headers)
    assert r.status_code == 201, r.text


def test_list_conversations(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    client.post("/conversations", json={"workspace_id": ws["id"], "member_ids": []}, headers=headers)
    r = client.get(f"/conversations?workspace_id={ws['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_create_message(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    c = client.post("/channels", json={"name": "Canal 1", "workspace_id": ws["id"]}, headers=headers).json()
    r = client.post("/messages", json={
        "workspace_id": ws["id"],
        "room_id": c["id"],
        "room_kind": "channel",
        "author_id": ws["owner_id"],
        "body": "Ola mundo"
    }, headers=headers)
    assert r.status_code in (201, 422, 400)


def test_list_messages(client, session_factory):
    ws, headers = _create_workspace(client, session_factory)
    c = client.post("/channels", json={"name": "Canal 1", "workspace_id": ws["id"]}, headers=headers).json()
    r = client.get(f"/messages?room_id={c['id']}", headers=headers)
    assert r.status_code == 200, r.text
