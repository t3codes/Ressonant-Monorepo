from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.common.email_outbox import process_outbox_batch
from app.common.security import hash_password
from app.config.settings import get_settings
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.domain.email_outbox import EmailOutbox
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent
from tests.conftest import login, make_user


def _seed(session_factory, *, seat_limit: int | None = 10, slug_suffix: str = ""):
    suffix = slug_suffix or uuid.uuid4().hex[:8]
    with session_factory() as db:
        org = Organization(
            name=f"Org {suffix}", slug=f"org-{suffix}", corporate_domain="example.com"
        )
        db.add(org)
        db.flush()
        owner_email = f"owner-{suffix}@x.com"
        owner_cpf = str(10000000000 + (uuid.uuid4().int % 89999999999))
        owner = User(
            email=owner_email,
            senha_hash=hash_password("senha-forte-1"),
            cpf=owner_cpf,
            telefone="11999990000",
            idade=30,
            termos_contrato=True,
            status_ativo=True,
        )
        db.add(owner)
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=org.id, user_id=owner.id, role="owner", status="active"
            )
        )
        ws = Workspace(
            name=f"WS {suffix}", slug=f"ws-{suffix}", owner_id=owner.id, organization_id=org.id
        )
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role="admin"))
        plan = Plan(
            code=f"p-{suffix}",
            name=f"P {suffix}",
            price_cents=0,
            currency="BRL",
            seat_limit=seat_limit,
            trial_days=14,
            active=True,
        )
        db.add(plan)
        db.flush()
        db.add(
            Subscription(
                organization_id=org.id, plan_id=plan.id, status="active", seats_purchased=0
            )
        )
        db.commit()
        return {"org_id": org.id, "ws_id": ws.id, "owner_email": owner_email}


def test_public_invitation_masks_email_and_resend_invalidates_token(client, session_factory):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    r = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "Guest@X.com",
            "nome_completo": "Convidado Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    )
    assert r.status_code == 201
    token = r.json()["token"]
    inv_id = r.json()["id"]

    pub = client.get(f"/invitations/{token}")
    assert pub.status_code == 200
    assert pub.json()["email_masked"] != "guest@x.com"
    assert "@" in pub.json()["email_masked"]

    r2 = client.post(f"/organizations/{ids['org_id']}/invitations/{inv_id}/resend", headers=headers)
    assert r2.status_code == 200
    new_token = r2.json()["token"]
    assert new_token != token
    old_pub = client.get(f"/invitations/{token}")
    assert old_pub.status_code == 404
    new_pub = client.get(f"/invitations/{new_token}")
    assert new_pub.status_code == 200


def test_register_invited_user_creates_identity_only_and_accepts(client, session_factory):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "new@x.com",
            "nome_completo": "Novo Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    ).json()
    token = inv["token"]

    r = client.post(
        "/auth/register/invitation",
        json={
            "token": token,
            "nome_completo": "New User",
            "cpf": "39053344705",
            "telefone": "11999990001",
            "senha": "senha-forte-1",
            "idade": 20,
            "termos_contrato": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"]
    assert body["organization_id"] == ids["org_id"]
    assert body["workspace_id"] == ids["ws_id"]

    with session_factory() as db:
        user = db.query(User).filter(User.email == "novo.exemplo@example.com").first()
        assert user is not None
        assert user.corporate_email == "novo.exemplo@example.com"
        assert user.personal_email == "new@x.com"
        orgs = db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).all()
        wss = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.id).all()
        assert len(orgs) == 1
        assert len(wss) == 1


def test_decline_and_state_transitions(client, session_factory):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "decline@x.com",
            "nome_completo": "Declinado Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    ).json()
    token = inv["token"]

    r = client.post(f"/invitations/{token}/decline")
    assert r.status_code == 200
    assert r.json()["status"] == "declined"

    # decline idempotent
    r2 = client.post(f"/invitations/{token}/decline")
    assert r2.status_code == 200
    assert r2.json()["status"] == "declined"

    # cannot accept declined
    make_user(session_factory, email="decline@x.com", cpf="16899535009")
    u_headers = login(client, "decline@x.com", "senha-forte-1")
    r3 = client.post(f"/invitations/{token}/accept", headers=u_headers)
    assert r3.status_code == 409
    assert r3.json()["error_code"] == "INVITATION_DECLINED"


def test_resend_and_revoke_endpoints_and_no_token_leak(client, session_factory):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "r@x.com",
            "nome_completo": "Reenvio Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    ).json()
    inv_id = inv["id"]
    token = inv["token"]

    listed = client.get(f"/organizations/{ids['org_id']}/invitations", headers=headers)
    assert listed.status_code == 200
    item = listed.json()[0]
    assert "token" not in item
    assert "token_hash" not in item
    assert item["send_status"] in {"pending", "sent", "failed", "not_configured", "skipped", None}

    resend = client.post(
        f"/organizations/{ids['org_id']}/invitations/{inv_id}/resend", headers=headers
    )
    assert resend.status_code == 200
    assert resend.json()["token"] != token
    assert "token_hash" not in resend.json()

    revoke = client.post(
        f"/organizations/{ids['org_id']}/invitations/{inv_id}/revoke", headers=headers
    )
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"
    # revoke again blocked
    revoke2 = client.post(
        f"/organizations/{ids['org_id']}/invitations/{inv_id}/revoke", headers=headers
    )
    assert revoke2.status_code == 409


def test_seat_limit_blocks_accept_and_register(client, session_factory):
    ids = _seed(session_factory, seat_limit=1)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    # create should fail due to seat limit
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "s@x.com",
            "nome_completo": "Assento Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    )
    assert inv.status_code == 409
    assert inv.json()["error_code"] == "SEAT_LIMIT_EXCEEDED"

    # seed with limit 2, create invite, then consume seat with another active member.
    ids2 = _seed(session_factory, seat_limit=2)
    headers2 = login(client, ids2["owner_email"], "senha-forte-1")
    inv2 = client.post(
        f"/organizations/{ids2['org_id']}/invitations",
        json={
            "email": "s2@x.com",
            "nome_completo": "Assento Dois Exemplo",
            "role": "member",
            "workspace_id": ids2["ws_id"],
        },
        headers=headers2,
    )
    assert inv2.status_code == 201
    token = inv2.json()["token"]
    # fill seat with another member
    with session_factory() as db:
        u = User(
            email="filler@x.com",
            senha_hash=hash_password("senha-forte-1"),
            cpf="11144477735",
            telefone="11999990002",
            idade=30,
            termos_contrato=True,
            status_ativo=True,
        )
        db.add(u)
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=ids2["org_id"], user_id=u.id, role="member", status="active"
            )
        )
        db.commit()

    make_user(session_factory, email="s2@x.com", cpf="16899535009")
    u2_headers = login(client, "s2@x.com", "senha-forte-1")
    acc = client.post(f"/invitations/{token}/accept", headers=u2_headers)
    assert acc.status_code == 409
    assert acc.json()["error_code"] == "SEAT_LIMIT_EXCEEDED"


def test_register_invitation_accepts_with_token_when_personal_email_has_account(
    client, session_factory
):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "dup@x.com",
            "nome_completo": "Duplicado Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    ).json()
    token = inv["token"]
    # A conta no e-mail pessoal não bloqueia o aceite: o token secreto e o CPF
    # válido bastam, e a nova identidade usa o e-mail corporativo reservado.
    existing = make_user(session_factory, email="dup@x.com", cpf="39053344705")
    r = client.post(
        "/auth/register/invitation",
        json={
            "token": token,
            "nome_completo": "Dup User",
            "cpf": "16899535009",
            "telefone": "11999990001",
            "senha": "senha-forte-1",
            "idade": 20,
            "termos_contrato": True,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["organization_id"] == ids["org_id"]
    assert r.json()["workspace_id"] == ids["ws_id"]

    with session_factory() as db:
        created = db.query(User).filter(User.email == "duplicado.exemplo@example.com").first()
        assert created is not None
        assert created.corporate_email == "duplicado.exemplo@example.com"
        assert created.personal_email == "dup@x.com"
        assert created.id != existing.id
        untouched = db.get(User, existing.id)
        assert untouched is not None
        assert untouched.email == "dup@x.com"
        assert untouched.cpf == "39053344705"


def test_outbox_retry_and_idempotency(client, session_factory, monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_PORT", "1025")
    get_settings.cache_clear()
    try:
        ids = _seed(session_factory)
        headers = login(client, ids["owner_email"], "senha-forte-1")
        inv = client.post(
            f"/organizations/{ids['org_id']}/invitations",
            json={
                "email": "out@x.com",
                "nome_completo": "Outbox Exemplo",
                "role": "member",
                "workspace_id": ids["ws_id"],
            },
            headers=headers,
        ).json()
        inv_id = inv["id"]

        # force outbox rows to be processable now
        with session_factory() as db:
            rows = db.query(EmailOutbox).all()
            assert rows
            for row in rows:
                row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                row.status = "pending"
            db.commit()

        calls = {"n": 0}

        def fake_send(**kwargs):
            calls["n"] += 1
            return False

        monkeypatch.setattr("app.common.email_outbox.send_invitation_email", fake_send)
        settings = get_settings()
        processed = process_outbox_batch(settings, session_factory=session_factory)
        assert processed >= 1
        with session_factory() as db:
            row = db.query(EmailOutbox).order_by(EmailOutbox.created_at.desc()).first()
            assert row is not None
            assert row.status == "failed"
            assert row.attempts == 1
            assert row.last_error
            inv_db = db.get(Invitation, inv_id)
            assert inv_db.send_status == "failed"

        # retry succeeds
        with session_factory() as db:
            row = db.query(EmailOutbox).order_by(EmailOutbox.created_at.desc()).first()
            assert row is not None
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()

        monkeypatch.setattr("app.common.email_outbox.send_invitation_email", lambda **kwargs: True)
        processed2 = process_outbox_batch(settings, session_factory=session_factory)
        assert processed2 >= 1
        with session_factory() as db:
            row = db.query(EmailOutbox).order_by(EmailOutbox.created_at.desc()).first()
            assert row is not None
            assert row.status == "sent"
            assert row.sent_at is not None
            inv_db = db.get(Invitation, inv_id)
            assert inv_db.send_status == "sent"
    finally:
        get_settings.cache_clear()


def test_invitation_audit_events_created(client, session_factory):
    ids = _seed(session_factory)
    headers = login(client, ids["owner_email"], "senha-forte-1")
    inv = client.post(
        f"/organizations/{ids['org_id']}/invitations",
        json={
            "email": "audit@x.com",
            "nome_completo": "Auditoria Exemplo",
            "role": "member",
            "workspace_id": ids["ws_id"],
        },
        headers=headers,
    ).json()
    inv_id = inv["id"]
    client.post(f"/organizations/{ids['org_id']}/invitations/{inv_id}/resend", headers=headers)
    client.post(f"/organizations/{ids['org_id']}/invitations/{inv_id}/revoke", headers=headers)
    with session_factory() as db:
        actions = {
            e.action for e in db.query(AuditEvent).filter(AuditEvent.entity_id == inv_id).all()
        }
        assert "invitation.created" in actions
        assert "invitation.resent" in actions
        assert "invitation.revoked" in actions
