from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.email_outbox import EmailOutbox
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.organization.usecases.corporate_email import (
    corporate_email_candidates,
    normalize_name_tokens,
)
from app.modules.teams.domain.models import Team
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, login, make_user

_INVITEE_NAME = "Convidado Teste"


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
        db.add(
            Organization(
                id=org_id,
                name="Acme",
                slug=f"acme-{uuid.uuid4().hex[:8]}",
                corporate_domain="example.com",
            )
        )
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
            "nome_completo": _INVITEE_NAME,
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
        json={
            "email": "third@example.com",
            "nome_completo": "Terceira Pessoa",
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
        json={
            "email": "invitee2@example.com",
            "nome_completo": "Segunda Pessoa",
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
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
            json={
                "email": "invitee@example.com",
                "nome_completo": _INVITEE_NAME,
                "role": "member",
                "workspace_id": ctx["ws_id"],
            },
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


def _create_invitation_for_rate_limit(
    client: TestClient, session_factory: sessionmaker[Session]
) -> tuple[dict[str, str], str]:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    create = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={
            "email": "invitee@example.com",
            "nome_completo": _INVITEE_NAME,
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    return headers, create.json()["token"]


def test_public_read_allows_twenty_gets_without_burning_mutation_bucket(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    headers, token = _create_invitation_for_rate_limit(client, session_factory)

    reads = [client.get(f"/invitations/{token}") for _ in range(20)]
    assert [resp.status_code for resp in reads] == [200] * 20

    accepts = [client.post(f"/invitations/{token}/accept", headers=headers) for _ in range(6)]
    assert [resp.status_code for resp in accepts[:5]] == [403] * 5
    blocked = accepts[5]
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["message"] == "Muitas tentativas. Aguarde antes de tentar novamente."
    assert body["error_code"] == "TOO_MANY_REQUESTS"
    assert "Error reference ID:" in body["detail"]


def test_public_read_keeps_abuse_protection(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, token = _create_invitation_for_rate_limit(client, session_factory)

    reads = [client.get(f"/invitations/{token}") for _ in range(51)]
    assert [resp.status_code for resp in reads[:50]] == [200] * 50
    assert reads[50].status_code == 429
    assert reads[50].json()["message"] == "Muitas tentativas. Aguarde antes de tentar novamente."


def test_decline_keeps_strict_rate_limit(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, token = _create_invitation_for_rate_limit(client, session_factory)

    declines = [client.post(f"/invitations/{token}/decline") for _ in range(6)]
    assert [resp.status_code for resp in declines[:5]] == [200] * 5
    blocked = declines[5]
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_REQUESTS"


def test_invite_registration_keeps_strict_rate_limit(client: TestClient) -> None:
    payload = {
        "token": "x" * 32,
        "nome_completo": "Convidado Teste",
        "cpf": "52998224725",
        "telefone": "11987654321",
        "senha": "senha-forte-1",
        "idade": 25,
        "termos_contrato": True,
    }
    responses = [client.post("/auth/register/invitation", json=payload) for _ in range(6)]
    assert [resp.status_code for resp in responses[:5]] == [404] * 5
    blocked = responses[5]
    assert blocked.status_code == 429
    assert blocked.json()["message"] == "Muitas tentativas. Tente novamente mais tarde."


def _invite(
    client: TestClient,
    ctx: dict[str, str],
    headers: dict[str, str],
    *,
    personal_email: str,
    name: str = _INVITEE_NAME,
    **extra: object,
):
    payload: dict[str, object] = {
        "email": personal_email,
        "nome_completo": name,
        "role": "member",
        "workspace_id": ctx["ws_id"],
    }
    payload.update(extra)
    return client.post(f"/organizations/{ctx['org_id']}/invitations", json=payload, headers=headers)


def _seed_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    cpf: str,
    corporate_email: str | None = None,
) -> None:
    user = make_user(session_factory, email=email, cpf=cpf)
    if corporate_email:
        with session_factory() as db:
            stored = db.get(User, user.id)
            assert stored is not None
            stored.corporate_email = corporate_email
            db.commit()


def test_corporate_email_cascade_order_and_numeric_suffix() -> None:
    tokens = normalize_name_tokens("José Carlos de Souza Júnior")
    assert tokens == ["jose", "carlos", "souza", "junior"]

    candidates = corporate_email_candidates(tokens, "Example.com", suffix_limit=2)
    assert candidates == [
        "jose.junior@example.com",
        "jose.carlos@example.com",
        "jose.c.junior@example.com",
        "jose.souza.junior@example.com",
        "jose.junior2@example.com",
        "jose.junior3@example.com",
    ]

    full = corporate_email_candidates(tokens, "example.com")
    assert full[-1] == "jose.junior1001@example.com"
    assert corporate_email_candidates(["joao"], "example.com")[1] == "joao.joao2@example.com"


def test_cascade_uses_second_third_and_fourth_formats_on_collisions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    name = "José Carlos de Souza Júnior"
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])

    first = _invite(client, ctx, headers, personal_email="first@example.com", name=name)
    assert first.status_code == 201, first.text
    assert first.json()["corporate_email"] == "jose.junior@example.com"

    _seed_user(session_factory, email="jose.junior@example.com", cpf="90000000001")
    second = _invite(client, ctx, headers, personal_email="second@example.com", name=name)
    assert second.status_code == 201, second.text
    assert second.json()["corporate_email"] == "jose.carlos@example.com"

    _seed_user(
        session_factory,
        email="user-corp-2@example.com",
        cpf="90000000002",
        corporate_email="jose.carlos@example.com",
    )
    third = _invite(client, ctx, headers, personal_email="third@example.com", name=name)
    assert third.status_code == 201, third.text
    assert third.json()["corporate_email"] == "jose.c.junior@example.com"

    _seed_user(session_factory, email="jose.c.junior@example.com", cpf="90000000003")
    fourth = _invite(client, ctx, headers, personal_email="fourth@example.com", name=name)
    assert fourth.status_code == 201, fourth.text
    assert fourth.json()["corporate_email"] == "jose.souza.junior@example.com"


def test_cascade_uses_numeric_suffix_after_pending_reservation_collision(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    name = "José Carlos de Souza Júnior"
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    for number, candidate in enumerate(
        (
            "jose.junior@example.com",
            "jose.carlos@example.com",
            "jose.c.junior@example.com",
            "jose.souza.junior@example.com",
        ),
        start=1,
    ):
        _seed_user(session_factory, email=f"taken-{number}@example.com", cpf=f"9010000000{number}")
        with session_factory() as db:
            stored = db.scalar(select(User).where(User.email == f"taken-{number}@example.com"))
            assert stored is not None
            stored.corporate_email = candidate
            db.commit()

    resp = _invite(client, ctx, headers, personal_email="homonym@example.com", name=name)
    assert resp.status_code == 201, resp.text
    assert resp.json()["corporate_email"] == "jose.junior2@example.com"

    next_resp = _invite(client, ctx, headers, personal_email="homonym-2@example.com", name=name)
    assert next_resp.status_code == 201, next_resp.text
    assert next_resp.json()["corporate_email"] == "jose.junior3@example.com"


def test_revoked_reservation_is_released_for_a_new_invitation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    name = "José Carlos de Souza Júnior"
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])

    first = _invite(client, ctx, headers, personal_email="first@example.com", name=name)
    assert first.json()["corporate_email"] == "jose.junior@example.com"
    revoke = client.post(
        f"/organizations/{ctx['org_id']}/invitations/{first.json()['id']}/revoke",
        headers=headers,
    )
    assert revoke.status_code == 200, revoke.text

    second = _invite(client, ctx, headers, personal_email="second@example.com", name=name)
    assert second.status_code == 201, second.text
    assert second.json()["corporate_email"] == "jose.junior@example.com"
    listed = client.get(f"/organizations/{ctx['org_id']}/invitations", headers=headers)
    assert listed.status_code == 200, listed.text
    active = [item for item in listed.json() if item["id"] == second.json()["id"]]
    assert len(active) == 1 and active[0]["reservation_active"] is True


def test_expired_reservation_is_released_by_expire_function(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    name = "José Carlos de Souza Júnior"
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])

    first = _invite(client, ctx, headers, personal_email="first@example.com", name=name)
    invitation_id = first.json()["id"]
    assert first.json()["corporate_email"] == "jose.junior@example.com"
    with session_factory() as db:
        invitation = db.get(Invitation, invitation_id)
        assert invitation is not None
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    with session_factory() as db:
        assert OrganizationRepository(db).expire_invitation_reservations() >= 1
        assert db.get(Invitation, invitation_id).reservation_active is False

    second = _invite(client, ctx, headers, personal_email="second@example.com", name=name)
    assert second.status_code == 201, second.text
    assert second.json()["corporate_email"] == "jose.junior@example.com"


def test_invitation_response_keeps_personal_email_as_recipient(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch
) -> None:
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    try:
        ctx = _seed_org_workspace(session_factory)
        headers = _auth(client, ctx["owner_email"])
        personal_email = "helena.pessoal@example.com"

        resp = _invite(
            client,
            ctx,
            headers,
            personal_email=personal_email,
            name="Helena Rocha",
        )
    finally:
        get_settings.cache_clear()
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == body["personal_email"] == personal_email
    assert body["corporate_email"] == "helena.rocha@example.com"
    assert body["invitee_name"] == "Helena Rocha"

    with session_factory() as db:
        outbox = db.scalar(select(EmailOutbox).where(EmailOutbox.recipient_email == personal_email))
        assert outbox is not None


def test_missing_domain_and_name_are_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    with session_factory() as db:
        organization = db.get(Organization, ctx["org_id"])
        assert organization is not None
        organization.corporate_domain = None
        db.commit()

    no_domain = _invite(client, ctx, headers, personal_email="p@example.com")
    assert no_domain.status_code == 422
    assert no_domain.json()["error_code"] == "CORPORATE_DOMAIN_NOT_CONFIGURED"

    no_name = client.post(
        f"/organizations/{ctx['org_id']}/invitations",
        json={
            "email": "p@example.com",
            "role": "member",
            "workspace_id": ctx["ws_id"],
        },
        headers=headers,
    )
    assert no_name.status_code == 422


def test_list_and_public_read_expose_names_without_personal_email(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    ctx = _seed_org_workspace(session_factory)
    headers = _auth(client, ctx["owner_email"])
    team_id = str(uuid.uuid4())
    with session_factory() as db:
        db.add(
            Team(
                id=team_id,
                name="Equipe Auditoria",
                slug=f"equipe-{uuid.uuid4().hex[:8]}",
                workspace_id=ctx["ws_id"],
                owner_id=ctx["owner_id"],
                key_prefix="AUD",
            )
        )
        db.commit()

    created = _invite(
        client,
        ctx,
        headers,
        personal_email="helena.pessoal@example.com",
        name="Helena Rocha",
        team_id=team_id,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["team_id"] == team_id
    assert body["team_name"] == "Equipe Auditoria"
    assert body["email_delivery_status"] in {"pending", "not_configured"}

    listed = client.get(f"/organizations/{ctx['org_id']}/invitations", headers=headers)
    assert listed.status_code == 200, listed.text
    item = listed.json()[0]
    assert item["personal_email"] == "helena.pessoal@example.com"
    assert item["corporate_email"] == "helena.rocha@example.com"
    assert item["invitee_name"] == "Helena Rocha"
    assert item["team_name"] == "Equipe Auditoria"
    assert item["reservation_active"] is True

    public = client.get(f"/invitations/{body['token']}")
    assert public.status_code == 200, public.text
    public_body = public.json()
    assert public_body["corporate_email"] == "helena.rocha@example.com"
    assert public_body["invitee_name"] == "Helena Rocha"
    assert public_body["team_name"] == "Equipe Auditoria"
    assert public_body["email_masked"] != "helena.pessoal@example.com"
    assert "team_id" not in public_body
