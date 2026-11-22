from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, login, make_user


def _seed_org_workspace(
    session_factory: sessionmaker[Session],
    *,
    owner_email: str = "owner@example.com",
    owner_cpf: str = VALID_CPFS[0],
    plan_code: str = "equipe",
    seat_limit: int | None = 15,
    seats_purchased: int = 0,
) -> dict[str, str]:
    owner = make_user(session_factory, email=owner_email, cpf=owner_cpf)
    org_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    with session_factory() as db:
        db.add(Organization(id=org_id, name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}"))
        db.add(
            OrganizationMember(
                organization_id=org_id, user_id=owner.id, role="owner", status="active"
            )
        )
        db.add(
            Workspace(
                id=ws_id,
                name="WS",
                slug=f"ws-{uuid.uuid4().hex[:8]}",
                owner_id=owner.id,
                organization_id=org_id,
            )
        )
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=owner.id, role="admin"))
        db.add(
            Plan(
                id=plan_id,
                code=plan_code,
                name=plan_code.title(),
                price_cents=0,
                currency="BRL",
                seat_limit=seat_limit,
                trial_days=14,
                active=True,
            )
        )
        db.add(
            Subscription(
                organization_id=org_id,
                plan_id=plan_id,
                status="trialing",
                seats_purchased=seats_purchased,
            )
        )
        db.commit()
    return {"org_id": org_id, "ws_id": ws_id, "owner_id": owner.id, "owner_email": owner_email}


def _auth(client: TestClient, email: str) -> dict[str, str]:
    return login(client, email)


def test_create_invitation_returns_token_once_and_persists_only_hash(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])

    resp = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["email"] == "invitee@example.com"
    assert "token" in body and len(body["token"]) > 20
    assert "token_hash" not in body

    with session_factory() as db:
        inv = db.get(Invitation, body["id"])
        assert inv is not None
        assert inv.token_hash != body["token"]
        assert len(inv.token_hash) == 64
        assert inv.email == "invitee@example.com"


def test_list_invitations_does_not_expose_token_or_hash(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    create = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=headers,
    )
    assert create.status_code == 201, create.text

    resp = client.get(f"/organizations/{ctx['org_id']}/invitations", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["email"] == "invitee@example.com"
    assert item["status"] == "pending"
    assert "token" not in item
    assert "token_hash" not in item


def test_accept_invitation_creates_memberships_and_marks_accepted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    owner_headers = _auth(client, ctx["owner_email"])
    invitee = make_user(session_factory, email="invitee@example.com", cpf=VALID_CPFS[1])
    invitee_headers = _auth(client, "invitee@example.com")

    create = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=owner_headers,
    )
    token = create.json()["token"]

    accept = client.post(f"/invitations/{token}/accept", headers=invitee_headers)
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["status"] == "accepted"
    assert body["organization_member_created"] is True
    assert body["workspace_member_created"] is True

    with session_factory() as db:
        inv = db.get(Invitation, create.json()["id"])
        assert inv is not None and inv.accepted_at is not None
        org_member = db.get(OrganizationMember, (ctx["org_id"], invitee.id))
        ws_member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["ws_id"],
                WorkspaceMember.user_id == invitee.id,
            )
        )
        assert org_member is not None and org_member.status == "active"
        assert ws_member is not None


def test_accept_rejects_reused_expired_revoked_and_email_mismatch(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    owner_headers = _auth(client, ctx["owner_email"])
    make_user(session_factory, email="invitee@example.com", cpf=VALID_CPFS[1])
    make_user(session_factory, email="other@example.com", cpf=VALID_CPFS[2])
    invitee_headers = _auth(client, "invitee@example.com")
    other_headers = _auth(client, "other@example.com")

    create = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=owner_headers,
    )
    token = create.json()["token"]

    mismatch = client.post(f"/invitations/{token}/accept", headers=other_headers)
    assert mismatch.status_code == 403
    assert mismatch.json()["error_code"] == "INVITATION_EMAIL_MISMATCH"

    ok = client.post(f"/invitations/{token}/accept", headers=invitee_headers)
    assert ok.status_code == 200
    reused = client.post(f"/invitations/{token}/accept", headers=invitee_headers)
    assert reused.status_code == 200
    assert reused.json()["organization_member_created"] is False
    assert reused.json()["workspace_member_created"] is False

    # expired
    create2 = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={
            "email": "invitee@example.com",
            "role": "member",
            "workspace_id": ctx["ws_id"],
            "expires_in_days": 1,
        },
        headers=owner_headers,
    )
    inv2_id = create2.json()["id"]
    token2 = create2.json()["token"]
    with session_factory() as db:
        inv2 = db.get(Invitation, inv2_id)
        assert inv2 is not None
        inv2.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    expired = client.post(f"/invitations/{token2}/accept", headers=invitee_headers)
    assert expired.status_code == 409
    assert expired.json()["error_code"] == "INVITATION_EXPIRED"

    # revoked
    make_user(session_factory, email="third@example.com", cpf=VALID_CPFS[3])
    third_headers = _auth(client, "third@example.com")
    create3 = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "third@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=owner_headers,
    )
    revoke = client.post(
        f"/organizations/{ctx['org_id']}/invitations/{create3.json()['id']}/revoke",
        headers=owner_headers,
    )
    assert revoke.status_code == 200
    revoked = client.post(f"/invitations/{create3.json()['token']}/accept", headers=third_headers)
    assert revoked.status_code == 409
    assert revoked.json()["error_code"] == "INVITATION_REVOKED"


def test_seat_limit_blocks_invitation_creation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory, plan_code="inicial", seat_limit=1, seats_purchased=0)
    headers = _auth(client, ctx["owner_email"])

    resp = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error_code"] == "SEAT_LIMIT_EXCEEDED"


def test_revoke_delete_and_access_control(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    make_user(session_factory, email="outsider@example.com", cpf=VALID_CPFS[1])
    outsider_headers = _auth(client, "outsider@example.com")

    create = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=headers,
    )
    inv_id = create.json()["id"]

    denied = client.get(f"/organizations/{ctx['org_id']}/invitations", headers=outsider_headers)
    assert denied.status_code in (403, 404)

    delete = client.delete(f"/organizations/{ctx['org_id']}/invitations/{inv_id}", headers=headers)
    assert delete.status_code == 204

    listed = client.get(f"/organizations/{ctx['org_id']}/invitations", headers=headers)
    assert listed.status_code == 200
    assert all(item["id"] != inv_id for item in listed.json())

    # outsider cannot create
    create2 = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={"email": "invitee2@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
        headers=outsider_headers,
    )
    assert create2.status_code in (403, 404)


def test_invite_secret_hidden_outside_development(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    try:
        ctx = _seed_org_workspace(session_factory)
        headers = _auth(client, ctx["owner_email"])
        resp = client.post(
            f"/organizations/{ctx['org_id']}/invitations",
            json={"email": "invitee@example.com", "role": "member", "workspace_id": ctx["ws_id"]},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["token"] is None
        assert body["invite_url"] is None
        assert "email_sent" in body

        resend = client.post(
            f"/organizations/{ctx['org_id']}/invitations/{body['id']}/resend",
            headers=headers,
        )
        assert resend.status_code == 200, resend.text
        resend_body = resend.json()
        assert resend_body["token"] is None
        assert resend_body["invite_url"] is None
    finally:
        get_settings.cache_clear()
