import pytest
from app.modules.chat.entrypoints import websocket as websocket_module
from app.modules.organization.domain.models import Organization, OrganizationMember
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user

ALLOWED_ORIGIN = "http://localhost:3000"


def _origin_headers() -> dict[str, str]:
    """Cada conexão precisa de um dict novo: o TestClient muta os headers."""
    return {"origin": ALLOWED_ORIGIN}


@pytest.fixture(autouse=True)
def _wire_websocket_revalidation(session_factory):
    """A revalidação na entrega usa o mesmo SQLite em memória dos testes."""
    websocket_module._revalidation_factory = session_factory
    websocket_module._cached_access.cache_clear()
    yield
    websocket_module._revalidation_factory = None


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
    membership = client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"user_id": member_id, "role": "member"},
        headers=owner_headers,
    )
    assert membership.status_code == 201, membership.text
    return channel, workspace, owner_headers, member_headers


def test_websocket_broadcasts_and_persists_between_room_members(
    client: TestClient, session_factory
) -> None:
    channel, workspace, owner_headers, member_headers = _create_channel(client, session_factory)
    owner_token = owner_headers["Authorization"].removeprefix("Bearer ")
    member_token = member_headers["Authorization"].removeprefix("Bearer ")

    with client.websocket_connect(
        f"/ws/channel/{channel['id']}",
        subprotocols=["bearer", owner_token],
        headers=_origin_headers(),
    ) as owner_socket:
        with client.websocket_connect(
            f"/ws/channel/{channel['id']}",
            subprotocols=["bearer", member_token],
            headers=_origin_headers(),
        ) as member_socket:
            owner_socket.send_json({"body": "Mensagem via WebSocket"})
            owner_event = owner_socket.receive_json()
            member_event = member_socket.receive_json()

    assert owner_event["type"] == member_event["type"] == "message.created"
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
        with client.websocket_connect(f"/ws/channel/{channel['id']}", headers=_origin_headers()):
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
            f"/ws/channel/{channel['id']}",
            subprotocols=["bearer", outsider_token],
            headers=_origin_headers(),
        ):
            pass
    assert forbidden.value.code == 4403


def _create_message_payload(room_id: str, **extra):
    return {
        "room_id": room_id,
        "room_kind": "channel",
        "body": "Mensagem via REST",
        **extra,
    }


def test_rest_message_publishes_message_created_to_room_subscribers(
    client: TestClient, session_factory
) -> None:
    channel, workspace, owner_headers, member_headers = _create_channel(client, session_factory)
    owner_token = owner_headers["Authorization"].removeprefix("Bearer ")
    member_token = member_headers["Authorization"].removeprefix("Bearer ")

    with client.websocket_connect(
        f"/ws/channel/{channel['id']}",
        subprotocols=["bearer", owner_token],
        headers=_origin_headers(),
    ) as owner_socket:
        with client.websocket_connect(
            f"/ws/channel/{channel['id']}",
            subprotocols=["bearer", member_token],
            headers=_origin_headers(),
        ) as member_socket:
            created = client.post(
                "/messages",
                json=_create_message_payload(channel["id"]),
                headers=owner_headers,
            )
            assert created.status_code == 201, created.text
            owner_event = owner_socket.receive_json()
            member_event = member_socket.receive_json()

    assert owner_event["type"] == member_event["type"] == "message.created"
    assert owner_event["message"]["id"] == created.json()["id"] == member_event["message"]["id"]


def test_rest_mention_creates_notification_with_workspace_context(
    client: TestClient, session_factory
) -> None:
    channel, workspace, owner_headers, member_headers = _create_channel(client, session_factory)
    member_token = member_headers["Authorization"].removeprefix("Bearer ")
    owner_id = client.get("/auth/me", headers=owner_headers).json()["id"]
    member_id = client.get("/auth/me", headers=member_headers).json()["id"]

    with client.websocket_connect(
        f"/ws/channel/{channel['id']}",
        subprotocols=["bearer", member_token],
        headers=_origin_headers(),
    ) as member_socket:
        created = client.post(
            "/messages",
            json=_create_message_payload(channel["id"], mention_ids=[member_id]),
            headers=owner_headers,
        )
        assert created.status_code == 201, created.text
        received = [member_socket.receive_json(), member_socket.receive_json()]
        events = {event["type"]: event for event in received}

    assert set(events) == {"message.created", "notification.created"}
    pushed = events["notification.created"]["notification"]
    assert pushed["workspace_id"] == workspace["id"]
    assert pushed["message_id"] == created.json()["id"]

    listing = client.get("/notifications", headers=member_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["kind"] == "mention"
    assert item["workspace_id"] == workspace["id"]
    assert item["actor_id"] == owner_id
    assert item["message_id"] == created.json()["id"]
    assert item["room_id"] == channel["id"]
    assert item["room_kind"] == "channel"


def test_thread_reply_notifies_parent_author_only(client: TestClient, session_factory) -> None:
    channel, workspace, owner_headers, member_headers = _create_channel(client, session_factory)
    member_id = client.get("/auth/me", headers=member_headers).json()["id"]

    root = client.post(
        "/messages",
        json=_create_message_payload(channel["id"], body="Pergunta"),
        headers=owner_headers,
    )
    assert root.status_code == 201, root.text

    reply = client.post(
        "/messages",
        json=_create_message_payload(
            channel["id"],
            body="Resposta",
            parent_id=root.json()["id"],
        ),
        headers=member_headers,
    )
    assert reply.status_code == 201, reply.text

    owner_notifications = client.get("/notifications", headers=owner_headers).json()
    assert owner_notifications["total"] == 1
    item = owner_notifications["items"][0]
    assert item["kind"] == "thread_reply"
    assert item["actor_id"] == member_id
    assert item["message_id"] == reply.json()["id"]
    assert item["workspace_id"] == workspace["id"]

    member_notifications = client.get("/notifications", headers=member_headers).json()
    assert member_notifications["total"] == 0
