"""CYB-WS-001/005: autor e workspace derivados do servidor; Origin validado na app."""

import uuid

import pytest
from app.modules.organization.domain.models import Organization, OrganizationMember
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user

ALLOWED_ORIGIN = "http://localhost:3000"


def _make_user(session_factory, *, email: str, cpf: str):
    user = _plain_make_user(session_factory, email=email, cpf=cpf)
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


def _workspace(client: TestClient, headers: dict[str, str], label: str) -> dict:
    response = client.post(
        "/workspaces",
        json={"name": f"Workspace {label}", "slug": f"ws-{label}-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _channel(client: TestClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = client.post(
        "/channels",
        json={"name": f"Canal {uuid.uuid4().hex[:8]}", "workspace_id": workspace_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup(client: TestClient, session_factory):
    owner = _make_user(session_factory, email="msg-owner@ressonant.dev", cpf="52998224725")
    member = _make_user(session_factory, email="msg-member@ressonant.dev", cpf="11144477735")
    outsider = _make_user(session_factory, email="msg-outsider@ressonant.dev", cpf="39053344705")
    _make_user(session_factory, email="msg-foreign@ressonant.dev", cpf="16899535009")
    owner_headers = login(client, "msg-owner@ressonant.dev")
    member_headers = login(client, "msg-member@ressonant.dev")
    outsider_headers = login(client, "msg-outsider@ressonant.dev")
    foreign_headers = login(client, "msg-foreign@ressonant.dev")
    workspace = _workspace(client, owner_headers, "owner")
    foreign_workspace = _workspace(client, foreign_headers, "foreign")
    channel = _channel(client, owner_headers, workspace["id"])
    foreign_channel = _channel(client, foreign_headers, foreign_workspace["id"])

    added = client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"user_id": member.id, "role": "member"},
        headers=owner_headers,
    )
    assert added.status_code == 201, added.text
    joined = client.post(
        f"/channels/{channel['id']}/members", params={"user_id": member.id}, headers=owner_headers
    )
    assert joined.status_code == 200, joined.text

    return {
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "workspace": workspace,
        "foreign_workspace": foreign_workspace,
        "channel": channel,
        "foreign_channel": foreign_channel,
        "owner_headers": owner_headers,
        "member_headers": member_headers,
        "outsider_headers": outsider_headers,
        "foreign_headers": foreign_headers,
    }


def _body(room_id: str, **extra):
    return {"room_id": room_id, "room_kind": "channel", "body": "Mensagem de teste", **extra}


def test_message_rejects_forged_author_and_workspace(client: TestClient, session_factory) -> None:
    ctx = _setup(client, session_factory)
    forged_author = client.post(
        "/messages",
        json=_body(ctx["channel"]["id"], author_id=ctx["outsider"].id),
        headers=ctx["owner_headers"],
    )
    assert forged_author.status_code == 422, forged_author.text

    forged_workspace = client.post(
        "/messages",
        json=_body(ctx["channel"]["id"], workspace_id=ctx["foreign_workspace"]["id"]),
        headers=ctx["owner_headers"],
    )
    assert forged_workspace.status_code == 422, forged_workspace.text


def test_message_derives_author_and_workspace_from_room_and_token(
    client: TestClient, session_factory
) -> None:
    ctx = _setup(client, session_factory)
    response = client.post(
        "/messages", json=_body(ctx["channel"]["id"]), headers=ctx["owner_headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["author_id"] == ctx["owner"].id
    assert body["workspace_id"] == ctx["workspace"]["id"]


def test_message_rejects_cross_workspace_and_nonmember(client: TestClient, session_factory) -> None:
    ctx = _setup(client, session_factory)

    cross = client.post(
        "/messages",
        json=_body(ctx["foreign_channel"]["id"]),
        headers=ctx["member_headers"],
    )
    assert cross.status_code == 403, cross.text
    assert cross.json()["error_code"] == "FORBIDDEN"

    nonmember = client.post(
        "/messages", json=_body(ctx["channel"]["id"]), headers=ctx["outsider_headers"]
    )
    assert nonmember.status_code == 403, nonmember.text

    stored = client.get(
        f"/messages?room_id={ctx['foreign_channel']['id']}", headers=ctx["foreign_headers"]
    ).json()
    assert stored["total"] == 0


def test_message_rejects_mention_of_nonmember(client: TestClient, session_factory) -> None:
    ctx = _setup(client, session_factory)
    response = client.post(
        "/messages",
        json=_body(ctx["channel"]["id"], mention_ids=[ctx["outsider"].id]),
        headers=ctx["owner_headers"],
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"


def test_websocket_rejects_origin_outside_cors(client: TestClient, session_factory) -> None:
    ctx = _setup(client, session_factory)
    token = ctx["owner_headers"]["Authorization"].removeprefix("Bearer ")
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
            f"/ws/channel/{ctx['channel']['id']}",
            subprotocols=["bearer", token],
            headers={"origin": "https://evil.example"},  # dict novo por conexão
        ):
            pass
    assert refused.value.code == 4403
