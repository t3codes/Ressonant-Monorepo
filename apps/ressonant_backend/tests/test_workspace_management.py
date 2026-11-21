from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.modules.workspace_management.domain.models import AuditEvent
from tests.conftest import VALID_CPFS, login, make_user


def _auth(client: TestClient, email: str) -> dict[str, str]:
    return login(client, email)


def _create_workspace(client: TestClient, headers: dict[str, str], slug: str, name: str = "Workspace") -> dict:
    resp = client.post("/workspaces", json={"name": name, "slug": slug}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_member(client: TestClient, headers: dict[str, str], workspace_id: str, user_id: str) -> dict:
    resp = client.post(
        f"/workspaces/{workspace_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _grant(
    client: TestClient,
    headers: dict[str, str],
    workspace_id: str,
    user_id: str,
    level: str,
    reason: str | None = None,
):
    payload = {"user_id": user_id, "level": level}
    if reason is not None:
        payload["reason"] = reason
    return client.post(f"/workspaces/{workspace_id}/management/grants", json=payload, headers=headers)


class TestAccessMe:
    def test_owner_gets_grant(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        headers = _auth(client, "owner@r.dev")
        ws = _create_workspace(client, headers, "ws-owner")

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "grant"
        assert body["is_owner"] is True
        assert body["capabilities"]["management_read"] is True
        assert body["capabilities"]["management_modify"] is True
        assert body["capabilities"]["management_grant"] is True

    def test_interno_adm_gets_grant(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        make_user(session_factory, email="adm@r.dev", cpf=VALID_CPFS[1], admin=True)
        owner_h = _auth(client, "owner@r.dev")
        adm_h = _auth(client, "adm@r.dev")
        ws = _create_workspace(client, owner_h, "ws-adm")

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=adm_h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "grant"
        assert body["interno_adm"] is True
        assert body["is_owner"] is False

    def test_member_without_grant_gets_none(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        member_h = _auth(client, "member@r.dev")
        ws = _create_workspace(client, owner_h, "ws-none")
        _add_member(client, owner_h, ws["id"], member.id)

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=member_h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "none"
        assert body["capabilities"]["management_read"] is False
        assert body["capabilities"]["management_modify"] is False
        assert body["capabilities"]["management_grant"] is False

    def test_member_with_read_grant(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        member_h = _auth(client, "member@r.dev")
        ws = _create_workspace(client, owner_h, "ws-read")
        _add_member(client, owner_h, ws["id"], member.id)

        grant_resp = _grant(client, owner_h, ws["id"], member.id, "read")
        assert grant_resp.status_code == 201, grant_resp.text

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=member_h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "read"
        assert body["capabilities"]["management_read"] is True
        assert body["capabilities"]["management_modify"] is False
        assert body["capabilities"]["management_grant"] is False

    def test_member_with_modify_grant(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        member_h = _auth(client, "member@r.dev")
        ws = _create_workspace(client, owner_h, "ws-modify")
        _add_member(client, owner_h, ws["id"], member.id)

        grant_resp = _grant(client, owner_h, ws["id"], member.id, "modify")
        assert grant_resp.status_code == 201, grant_resp.text

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=member_h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "modify"
        assert body["capabilities"]["management_read"] is True
        assert body["capabilities"]["management_modify"] is True
        assert body["capabilities"]["management_grant"] is False

    def test_member_with_grant_level(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        member_h = _auth(client, "member@r.dev")
        ws = _create_workspace(client, owner_h, "ws-grant")
        _add_member(client, owner_h, ws["id"], member.id)

        grant_resp = _grant(client, owner_h, ws["id"], member.id, "grant")
        assert grant_resp.status_code == 201, grant_resp.text

        resp = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=member_h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["level"] == "grant"
        assert body["capabilities"]["management_read"] is True
        assert body["capabilities"]["management_modify"] is True
        assert body["capabilities"]["management_grant"] is True


class TestGrantsRead:
    def test_list_grants_denied_without_management_read(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        member_h = _auth(client, "member@r.dev")
        ws = _create_workspace(client, owner_h, "ws-grants-deny")
        _add_member(client, owner_h, ws["id"], member.id)

        resp = client.get(f"/workspaces/{ws['id']}/management/grants", headers=member_h)
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error_code"] == "MANAGEMENT_ACCESS_DENIED"
        assert body["error_layer"] == "management"
        assert body["required_capability"] == "management.read"


class TestGrantsWriteR9:
    def test_member_grant_can_grant_read_and_modify(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        granter = make_user(session_factory, email="granter@r.dev", cpf=VALID_CPFS[1])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[2])
        owner_h = _auth(client, "owner@r.dev")
        granter_h = _auth(client, "granter@r.dev")
        ws = _create_workspace(client, owner_h, "ws-r9-ok")
        _add_member(client, owner_h, ws["id"], granter.id)
        _add_member(client, owner_h, ws["id"], target.id)

        assert _grant(client, owner_h, ws["id"], granter.id, "grant").status_code == 201

        r1 = _grant(client, granter_h, ws["id"], target.id, "read")
        assert r1.status_code == 201, r1.text
        assert r1.json()["level"] == "read"

        r2 = _grant(client, granter_h, ws["id"], target.id, "modify")
        assert r2.status_code == 201, r2.text
        assert r2.json()["level"] == "modify"

    def test_member_grant_cannot_grant_grant_level(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        granter = make_user(session_factory, email="granter@r.dev", cpf=VALID_CPFS[1])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[2])
        owner_h = _auth(client, "owner@r.dev")
        granter_h = _auth(client, "granter@r.dev")
        ws = _create_workspace(client, owner_h, "ws-r9-deny")
        _add_member(client, owner_h, ws["id"], granter.id)
        _add_member(client, owner_h, ws["id"], target.id)
        assert _grant(client, owner_h, ws["id"], granter.id, "grant").status_code == 201

        resp = _grant(client, granter_h, ws["id"], target.id, "grant")
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error_code"] == "MANAGEMENT_GRANT_ESCALATION_DENIED"
        assert body["error_layer"] == "management"

    def test_owner_can_grant_grant_level(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        ws = _create_workspace(client, owner_h, "ws-owner-grant")
        _add_member(client, owner_h, ws["id"], target.id)

        resp = _grant(client, owner_h, ws["id"], target.id, "grant")
        assert resp.status_code == 201, resp.text
        assert resp.json()["level"] == "grant"


class TestRevokeR9AndEffect:
    def test_member_grant_cannot_revoke_grant_level(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        granter = make_user(session_factory, email="granter@r.dev", cpf=VALID_CPFS[1])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[2])
        owner_h = _auth(client, "owner@r.dev")
        granter_h = _auth(client, "granter@r.dev")
        ws = _create_workspace(client, owner_h, "ws-revoke-r9")
        _add_member(client, owner_h, ws["id"], granter.id)
        _add_member(client, owner_h, ws["id"], target.id)
        assert _grant(client, owner_h, ws["id"], granter.id, "grant").status_code == 201
        assert _grant(client, owner_h, ws["id"], target.id, "grant").status_code == 201

        resp = client.request(
            "DELETE",
            f"/workspaces/{ws['id']}/management/grants/{target.id}",
            headers=granter_h,
            json={},
        )
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error_code"] == "MANAGEMENT_GRANT_ESCALATION_DENIED"
        assert body["error_layer"] == "management"

    def test_revoke_invalidates_effective_access(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[1])
        owner_h = _auth(client, "owner@r.dev")
        target_h = _auth(client, "target@r.dev")
        ws = _create_workspace(client, owner_h, "ws-revoke-effect")
        _add_member(client, owner_h, ws["id"], target.id)
        assert _grant(client, owner_h, ws["id"], target.id, "modify").status_code == 201

        before = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=target_h)
        assert before.status_code == 200
        assert before.json()["level"] == "modify"

        revoke = client.request(
            "DELETE",
            f"/workspaces/{ws['id']}/management/grants/{target.id}",
            headers=owner_h,
            json={},
        )
        assert revoke.status_code == 204, revoke.text

        after = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=target_h)
        assert after.status_code == 200, after.text
        assert after.json()["level"] == "none"
        assert after.json()["capabilities"]["management_read"] is False


class TestInternoAdmBreakGlass:
    def test_break_glass_requires_reason(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[1])
        make_user(session_factory, email="adm@r.dev", cpf=VALID_CPFS[2], admin=True)
        owner_h = _auth(client, "owner@r.dev")
        adm_h = _auth(client, "adm@r.dev")
        ws = _create_workspace(client, owner_h, "ws-bg-reason")
        _add_member(client, owner_h, ws["id"], target.id)

        resp = _grant(client, adm_h, ws["id"], target.id, "read")
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["error_code"] == "BREAK_GLASS_REASON_REQUIRED"
        assert body["error_layer"] == "management"

    def test_break_glass_with_reason_succeeds_and_audits(self, client: TestClient, session_factory) -> None:
        make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
        target = make_user(session_factory, email="target@r.dev", cpf=VALID_CPFS[1])
        adm = make_user(session_factory, email="adm@r.dev", cpf=VALID_CPFS[2], admin=True)
        owner_h = _auth(client, "owner@r.dev")
        adm_h = _auth(client, "adm@r.dev")
        ws = _create_workspace(client, owner_h, "ws-bg-ok")
        _add_member(client, owner_h, ws["id"], target.id)

        resp = _grant(client, adm_h, ws["id"], target.id, "read", reason="suporte emergencial")
        assert resp.status_code == 201, resp.text
        assert resp.json()["level"] == "read"

        with session_factory() as db:
            events = list(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.workspace_id == ws["id"],
                        AuditEvent.action == "management.grant.upsert",
                        AuditEvent.actor_user_id == adm.id,
                    )
                )
            )
        assert len(events) >= 1
        event = events[-1]
        assert event.actor_type == "internal_admin"
        assert event.result == "success"
        assert event.target_user_id == target.id
        assert isinstance(event.metadata_, dict)
        assert event.metadata_.get("break_glass") is True
        assert event.metadata_.get("reason") == "suporte emergencial"
