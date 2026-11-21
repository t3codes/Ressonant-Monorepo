import pytest
from app.modules.organization.domain.models import Organization, OrganizationMember
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
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


def _create_channel(client: TestClient, session_factory):
    make_user(session_factory, email="owner@ressonant.dev", cpf="52998224725")
    owner_headers = login(client, "owner@ressonant.dev")
    workspace = client.post(
        "/workspaces",
        json={"name": "Workspace WS", "slug": "workspace-ws"},
        headers=owner_headers,
    ).json()
    channel = client.post(
        "/channels",
        json={"name": "Canal WS", "workspace_id": workspace["id"]},
        headers=owner_headers,
    ).json()
    make_user(
        session_factory,
        email="member@ressonant.dev",
        cpf="11144477735",
    )
    member_headers = login(client, "member@ressonant.dev")
    member_id = client.get("/auth/me", headers=member_headers).json()["id"]
    added = client.post(
        f"/channels/{channel['id']}/members",
        params={"user_id": member_id},
        headers=owner_headers,
    )
    assert added.status_code == 200, added.text
    return channel, workspace, owner_headers, member_headers


def test_websocket_broadcasts_and_persists_between_room_members(
    client: TestClient, session_factory
) -> None:
    channel, workspace, owner_headers, member_headers = _create_channel(client, session_factory)
    owner_token = owner_headers["Authorization"].removeprefix("Bearer ")
    member_token = member_headers["Authorization"].removeprefix("Bearer ")

    with client.websocket_connect(
        f"/ws/channel/{channel['id']}", subprotocols=["bearer", owner_token]
    ) as owner_socket:
        with client.websocket_connect(
            f"/ws/channel/{channel['id']}", subprotocols=["bearer", member_token]
        ) as member_socket:
            owner_socket.send_json({"body": "Mensagem via WebSocket"})
            owner_event = owner_socket.receive_json()
            member_event = member_socket.receive_json()

    assert owner_event["type"] == member_event["type"] == "message"
    assert owner_event["message"]["id"] == member_event["message"]["id"]
    assert owner_event["message"]["body"] == "Mensagem via WebSocket"

    persisted = client.get(f"/messages?room_id={channel['id']}", headers=owner_headers)
    assert persisted.status_code == 200
    assert persisted.json()["total"] == 1
    assert persisted.json()["items"][0]["workspace_id"] == workspace["id"]


def test_websocket_rejects_missing_or_nonmember_credentials(
    client: TestClient, session_factory
) -> None:
    channel, _, _, _ = _create_channel(client, session_factory)
    with pytest.raises(WebSocketDisconnect) as missing_token:
        with client.websocket_connect(f"/ws/channel/{channel['id']}"):
            pass
    assert missing_token.value.code == 4401

    make_user(
        session_factory,
        email="outsider@ressonant.dev",
        cpf="39053344705",
    )
    outsider_headers = login(client, "outsider@ressonant.dev")
    outsider_token = outsider_headers["Authorization"].removeprefix("Bearer ")
    with pytest.raises(WebSocketDisconnect) as forbidden:
        with client.websocket_connect(
            f"/ws/channel/{channel['id']}", subprotocols=["bearer", outsider_token]
        ):
            pass
    assert forbidden.value.code == 4403
