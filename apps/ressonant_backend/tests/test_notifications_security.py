"""CYB-WS-004: caixa de notificações escopada ao usuário autenticado."""

import uuid

from app.modules.notifications.domain.models import AppNotification
from app.modules.organization.domain.models import Organization, OrganizationMember
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user


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
    owner = _make_user(session_factory, email="notif-owner@ressonant.dev", cpf="52998224725")
    other = _make_user(session_factory, email="notif-other@ressonant.dev", cpf="11144477735")
    owner_headers = login(client, "notif-owner@ressonant.dev")
    other_headers = login(client, "notif-other@ressonant.dev")
    workspace = _workspace(client, owner_headers, "owner")
    other_workspace = _workspace(client, other_headers, "other")
    return owner, other, owner_headers, other_headers, workspace, other_workspace


def test_post_notification_requires_authentication(client: TestClient, session_factory) -> None:
    _, _, _, _, workspace, _ = _setup(client, session_factory)
    response = client.post(
        "/notifications",
        json={"kind": "system", "title": "Aviso", "workspace_id": workspace["id"]},
    )
    assert response.status_code == 401


def test_post_notification_fixes_user_id_and_rejects_forged_actor(
    client: TestClient, session_factory
) -> None:
    owner, other, headers, _, workspace, _ = _setup(client, session_factory)
    body = {"kind": "system", "title": "Aviso", "workspace_id": workspace["id"]}

    forged = client.post("/notifications", json={**body, "actor_id": other.id}, headers=headers)
    assert forged.status_code == 403, forged.text
    assert forged.json()["error_code"] == "FORBIDDEN"

    mass_assignment = client.post(
        "/notifications", json={**body, "user_id": other.id}, headers=headers
    )
    assert mass_assignment.status_code == 422

    created = client.post("/notifications", json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["user_id"] == owner.id
    assert created.json()["actor_id"] == owner.id


def test_post_notification_validates_workspace_and_room(
    client: TestClient, session_factory
) -> None:
    _, _, owner_headers, other_headers, workspace, other_workspace = _setup(client, session_factory)
    foreign = client.post(
        "/notifications",
        json={
            "kind": "system",
            "title": "Aviso",
            "workspace_id": other_workspace["id"],
        },
        headers=owner_headers,
    )
    assert foreign.status_code == 403, foreign.text

    channel = _channel(client, other_headers, other_workspace["id"])
    cross_room = client.post(
        "/notifications",
        json={
            "kind": "system",
            "title": "Aviso",
            "workspace_id": workspace["id"],
            "room_id": channel["id"],
            "room_kind": "channel",
        },
        headers=owner_headers,
    )
    assert cross_room.status_code == 404, cross_room.text

    missing_room = client.post(
        "/notifications",
        json={
            "kind": "system",
            "title": "Aviso",
            "workspace_id": workspace["id"],
            "room_id": str(uuid.uuid4()),
            "room_kind": "channel",
        },
        headers=owner_headers,
    )
    assert missing_room.status_code == 404, missing_room.text


def test_mark_read_is_scoped_to_the_authenticated_user(client: TestClient, session_factory) -> None:
    owner, other, owner_headers, other_headers, workspace, _ = _setup(client, session_factory)
    with session_factory() as db:
        notification = AppNotification(
            user_id=other.id,
            kind="system",
            title="Privada",
            body="conteúdo do outro usuário",
            workspace_id=workspace["id"],
        )
        db.add(notification)
        db.commit()
        notification_id = notification.id

    forbidden = client.patch(
        "/notifications/mark-read", json=[notification_id], headers=owner_headers
    )
    assert forbidden.status_code == 400, forbidden.text
    assert forbidden.json()["error_code"] == "NOTIFICATION_NOT_FOUND"

    with session_factory() as db:
        row = db.scalar(select(AppNotification).where(AppNotification.id == notification_id))
        assert row is not None and row.read_at is None

    allowed = client.patch(
        "/notifications/mark-read", json=[notification_id], headers=other_headers
    )
    assert allowed.status_code == 204, allowed.text
    with session_factory() as db:
        row = db.scalar(select(AppNotification).where(AppNotification.id == notification_id))
        assert row is not None and row.read_at is not None

    owner_all = client.patch("/notifications/mark-all-read", headers=owner_headers)
    assert owner_all.status_code == 204
    with session_factory() as db:
        row = db.scalar(select(AppNotification).where(AppNotification.id == notification_id))
        assert row is not None and row.read_at is not None
