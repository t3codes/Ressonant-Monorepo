"""CYB-WS-002/003: envelope assinado, canal vinculado ao payload e revogação na entrega."""

import uuid

import pytest
from app.common.realtime import (
    RealtimeBus,
    get_realtime_bus,
    new_event,
    room_channel,
    sign_event,
    user_channel,
    validate_envelope,
    verify_event,
)
from app.modules.chat.domain.models import Channel
from app.modules.chat.entrypoints import websocket as websocket_module
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user

ALLOWED_ORIGIN = "http://localhost:3000"


@pytest.fixture(autouse=True)
def _wire_revalidation(session_factory):
    websocket_module._revalidation_factory = session_factory
    websocket_module._cached_access.cache_clear()
    yield
    websocket_module._revalidation_factory = None
    websocket_module._cached_access.cache_clear()


def _message_event(room_id: str, workspace_id: str) -> dict:
    return new_event(
        "message.created",
        "message",
        {"room_kind": "channel", "room_id": room_id, "workspace_id": workspace_id},
    )


def test_signature_is_channel_bound_and_domain_separated() -> None:
    channel = room_channel("channel", str(uuid.uuid4()))
    event = _message_event(str(uuid.uuid4()), str(uuid.uuid4()))
    signed = sign_event(channel, event)

    assert validate_envelope(channel, signed).type == "message.created"
    assert verify_event(channel, signed)
    assert not verify_event(user_channel("someone"), signed)

    other = sign_event(user_channel("someone"), event)
    assert signed["signature"] != other["signature"]

    tampered = {**signed, "body": "conteúdo alterado"}
    assert not verify_event(channel, tampered)
    with pytest.raises(ValueError):
        validate_envelope(channel, tampered)


def test_unsigned_event_is_not_delivered_by_local_fanout() -> None:
    channel = room_channel("channel", str(uuid.uuid4()))
    event = _message_event(str(uuid.uuid4()), str(uuid.uuid4()))
    received: list[dict] = []
    bus = RealtimeBus()
    unregister = bus.register(channel, lambda _channel, payload: received.append(payload))

    bus._deliver(channel, event)
    assert received == []

    bus.publish(channel, event)
    assert len(received) == 1
    unregister()


def test_revoked_user_is_disconnected_on_delivery(client: TestClient, session_factory) -> None:
    user = _plain_make_user(session_factory, email="revoke@ressonant.dev", cpf="52998224725")
    with session_factory() as db:
        organization = Organization(name="Org revoke", slug="org-revoke")
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

    headers = login(client, "revoke@ressonant.dev")
    workspace = client.post(
        "/workspaces",
        json={"name": "Ws revoke", "slug": f"ws-revoke-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    ).json()
    channel = client.post(
        "/channels",
        json={"name": "Canal revoke", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()
    token = headers["Authorization"].removeprefix("Bearer ")

    with client.websocket_connect(
        f"/ws/channel/{channel['id']}",
        subprotocols=["bearer", token],
        headers={"origin": ALLOWED_ORIGIN},
    ) as socket:
        with session_factory() as db:
            row = db.get(User, user.id)
            row.status_ativo = False
            db.commit()
        websocket_module._cached_access.cache_clear()

        from app.common.realtime import get_realtime_bus

        get_realtime_bus().publish(
            room_channel("channel", channel["id"]),
            _message_event(channel["id"], workspace["id"]),
        )
        with pytest.raises(WebSocketDisconnect) as revoked:
            socket.receive_json()
        assert revoked.value.code == 4403


def _room_user(session_factory, *, email, cpf, label):
    user = _plain_make_user(session_factory, email=email, cpf=cpf)
    with session_factory() as db:
        organization = Organization(name=f"Org {label}", slug=f"org-{label}-{uuid.uuid4().hex[:8]}")
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


def _create_room(client, session_factory, *, email, cpf, label):
    user = _room_user(session_factory, email=email, cpf=cpf, label=label)
    headers = login(client, email)
    workspace = client.post(
        "/workspaces",
        json={"name": f"Ws {label}", "slug": f"ws-{label}-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    ).json()
    channel = client.post(
        "/channels",
        json={"name": f"Canal {label}", "workspace_id": workspace["id"]},
        headers=headers,
    ).json()
    return user, headers, workspace, channel


def _connect(client, room_id, headers):
    token = headers["Authorization"].removeprefix("Bearer ")
    return client.websocket_connect(
        f"/ws/channel/{room_id}",
        subprotocols=["bearer", token],
        headers={"origin": ALLOWED_ORIGIN},
    )


def _publish_room_event(workspace, channel):
    get_realtime_bus().publish(
        room_channel("channel", channel["id"]),
        _message_event(channel["id"], workspace["id"]),
    )


def _assert_revocation_cleanup(user, workspace, channel):
    assert room_channel("channel", channel["id"]) not in websocket_module._channel_refs
    assert user_channel(user.id) not in websocket_module._channel_refs
    assert not any(
        connection.user_id == user.id
        for connections in websocket_module.manager._rooms.values()
        for connection in connections
    )
    assert not any(
        connection.user_id == user.id
        for connections in websocket_module.manager._users.values()
        for connection in connections
    )


def _assert_dispatcher_and_other_room_survive(client, session_factory):
    task = websocket_module._task
    assert task is not None
    assert not task.done()

    _, healthy_headers, healthy_workspace, healthy_channel = _create_room(
        client,
        session_factory,
        email="dispatcher-alive@ressonant.dev",
        cpf="11144477735",
        label="dispatcher-alive",
    )
    with _connect(client, healthy_channel["id"], healthy_headers) as healthy_socket:
        _publish_room_event(healthy_workspace, healthy_channel)
        event = healthy_socket.receive_json()

    assert event["type"] == "message.created"
    assert event["message"]["room_id"] == healthy_channel["id"]
    assert not task.done()


def test_revoked_member_is_disconnected_and_dispatcher_survives(
    client: TestClient, session_factory
) -> None:
    user, headers, workspace, channel = _create_room(
        client,
        session_factory,
        email="member-revoked@ressonant.dev",
        cpf="52998224725",
        label="member-revoked",
    )
    with _connect(client, channel["id"], headers) as socket:
        with session_factory() as db:
            member = db.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace["id"],
                    WorkspaceMember.user_id == user.id,
                )
            )
            assert member is not None
            db.delete(member)
            db.commit()
        websocket_module._cached_access.cache_clear()

        _publish_room_event(workspace, channel)
        with pytest.raises(WebSocketDisconnect) as revoked:
            socket.receive_json()
        assert revoked.value.code == 4403
        _assert_revocation_cleanup(user, workspace, channel)
        _assert_dispatcher_and_other_room_survive(client, session_factory)


def test_revoked_workspace_is_disconnected_and_dispatcher_survives(
    client: TestClient, session_factory
) -> None:
    user, headers, workspace, channel = _create_room(
        client,
        session_factory,
        email="workspace-revoked@ressonant.dev",
        cpf="52998224725",
        label="workspace-revoked",
    )
    with _connect(client, channel["id"], headers) as socket:
        with session_factory() as db:
            row = db.get(Workspace, workspace["id"])
            assert row is not None
            row.status_ativo = False
            db.commit()
        websocket_module._cached_access.cache_clear()

        _publish_room_event(workspace, channel)
        with pytest.raises(WebSocketDisconnect) as revoked:
            socket.receive_json()
        assert revoked.value.code == 4403
        _assert_revocation_cleanup(user, workspace, channel)
        _assert_dispatcher_and_other_room_survive(client, session_factory)


def test_revoked_room_is_disconnected_and_dispatcher_survives(
    client: TestClient, session_factory
) -> None:
    user, headers, workspace, channel = _create_room(
        client,
        session_factory,
        email="room-revoked@ressonant.dev",
        cpf="52998224725",
        label="room-revoked",
    )
    with _connect(client, channel["id"], headers) as socket:
        with session_factory() as db:
            row = db.get(Channel, channel["id"])
            assert row is not None
            row.status_ativo = False
            db.commit()
        websocket_module._cached_access.cache_clear()

        _publish_room_event(workspace, channel)
        with pytest.raises(WebSocketDisconnect) as revoked:
            socket.receive_json()
        assert revoked.value.code == 4403
        _assert_revocation_cleanup(user, workspace, channel)
        _assert_dispatcher_and_other_room_survive(client, session_factory)
