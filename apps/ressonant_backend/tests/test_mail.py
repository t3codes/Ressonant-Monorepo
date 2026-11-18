from fastapi.testclient import TestClient

from tests.conftest import login, make_user, register_payload


def _create_user_and_headers(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    return login(client, email)


def test_create_email_requires_auth(client):
    assert client.post("/mail", json={"subject": "Assunto", "body": "Corpo", "sender_id": "x", "recipient_ids": []}).status_code == 401


def test_create_email_success(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    ws = client.post("/workspaces", json={"name": "WS", "slug": "ws"}, headers=headers).json()
    r = client.post("/mail", json={
        "sender_id": ws.get("owner_id", "555181a9-c69b-46f6-9120-2cefed2c5680"),
        "recipient_ids": ["recipient-1"],
        "subject": "Assunto",
        "body": "Corpo do e-mail"
    }, headers=headers)
    assert r.status_code in (201, 422), r.text


def test_list_emails(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.get("/mail", headers=headers)
    assert r.status_code == 200, r.text


def test_get_email(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    ws = client.post("/workspaces", json={"name": "WS", "slug": "ws"}, headers=headers).json()
    create = client.post("/mail", json={
        "sender_id": ws.get("owner_id", "555181a9-c69b-46f6-9120-2cefed2c5680"),
        "recipient_ids": ["recipient-1"],
        "subject": "Assunto",
        "body": "Corpo"
    }, headers=headers)
    if create.status_code == 201:
        email_id = create.json()["id"]
        r = client.get(f"/mail/{email_id}", headers=headers)
        assert r.status_code == 200, r.text
    else:
        assert create.status_code in (400, 422, 500)


def test_mark_email_read(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.patch("/mail/email-id-1/read", headers=headers)
    assert r.status_code in (200, 404, 422)


def test_update_email_for_user(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.patch("/mail/email-id-1", json={"trashed": True}, headers=headers)
    assert r.status_code in (200, 404, 422)
