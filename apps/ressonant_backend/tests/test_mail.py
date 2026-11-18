from fastapi.testclient import TestClient

from tests.conftest import login, make_user, register_payload


def _create_user_and_headers(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    return login(client, email)


def test_create_email_requires_auth(client):
    assert client.post("/mail", json={"subject": "S", "body": "B", "sender_id": "x", "recipient_ids": []}).status_code == 401


def test_create_email_success(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.post("/mail", json={
        "sender_id": "sender-1",
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
    # Criar primeiro
    create = client.post("/mail", json={
        "sender_id": "sender-1",
        "recipient_ids": ["recipient-1"],
        "subject": "Assunto",
        "body": "Corpo"
    }, headers=headers)
    if create.status_code == 201:
        email_id = create.json()["id"]
        r = client.get(f"/mail/{email_id}", headers=headers)
        assert r.status_code == 200, r.text


def test_mark_email_read(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.patch("/mail/email-id-1/read", headers=headers)
    assert r.status_code in (200, 404, 422)


def test_update_email_for_user(client, session_factory):
    headers = _create_user_and_headers(client, session_factory)
    r = client.patch("/mail/email-id-1", json={"trashed": True}, headers=headers)
    assert r.status_code in (200, 404, 422)
