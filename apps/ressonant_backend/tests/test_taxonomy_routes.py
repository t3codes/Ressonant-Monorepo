from __future__ import annotations

import json
import uuid

from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.workspace.domain.models import Workspace
from app.modules.workspace_management.domain.models import (
    AuditEvent,
    CardTaxonomyModel,
    WorkspaceTaxonomyGrantModel,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.conftest import VALID_CPFS, login
from tests.conftest import make_user as _plain_make_user

SENSITIVE_REASON = "JUSTIFICATIVA-SENSIVEL-TAX-TEST"
AUDIT_FORBIDDEN = (SENSITIVE_REASON, "senha_hash", "cpf", "telefone", "@ressonant.dev", "<script>")


def make_user(session_factory, **kwargs):
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


def _auth(client: TestClient, email: str) -> dict[str, str]:
    return login(client, email)


def _workspace(client: TestClient, headers: dict[str, str]) -> dict:
    resp = client.post(
        "/workspaces",
        json={"name": "Workspace Tax", "slug": f"ws-tax-{uuid.uuid4().hex[:10]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_member(
    client: TestClient, headers: dict[str, str], workspace_id: str, user_id: str
) -> None:
    resp = client.post(
        f"/workspaces/{workspace_id}/members", json={"user_id": user_id}, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text


def _create_value(
    client: TestClient, headers: dict[str, str], workspace_id: str, name: str = "Bug"
) -> dict:
    resp = client.post(
        f"/workspaces/{workspace_id}/management/taxonomy",
        json={"kind": "category", "name": name, "color": "#123456"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _send(client: TestClient, method: str, url: str, payload: dict | None, headers: dict[str, str]):
    return client.request(method.upper(), url, json=payload, headers=headers)


def _error(body: dict) -> tuple[int | None, str | None, str | None]:
    return body.get("status_code"), body.get("error_code"), body.get("message")


def _audit_rows(session_factory, workspace_id: str) -> list[AuditEvent]:
    with session_factory() as db:
        return list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.workspace_id == workspace_id)
                .order_by(AuditEvent.occurred_at)
            )
        )


def _workspace_organization_id(session_factory, workspace_id: str) -> str:
    with session_factory() as db:
        organization_id = db.scalar(
            select(Workspace.organization_id).where(Workspace.id == workspace_id)
        )
        assert organization_id
        return organization_id


def _set_organization_role(session_factory, organization_id: str, user_id: str, role: str) -> None:
    with session_factory() as db:
        membership = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        if membership is None:
            db.add(
                OrganizationMember(
                    organization_id=organization_id,
                    user_id=user_id,
                    role=role,
                    status="active",
                )
            )
        else:
            membership.role = role
            membership.status = "active"
        db.commit()


def test_all_routes_require_token(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    ws = _workspace(client, _auth(client, "owner@r.dev"))
    base = f"/workspaces/{ws['id']}/management"
    calls: list[tuple[str, str, dict | None]] = [
        ("GET", f"{base}/taxonomy?kind=category", None),
        ("POST", f"{base}/taxonomy", {"kind": "category", "name": "Bug"}),
        ("PATCH", f"{base}/taxonomy/{uuid.uuid4()}", {"color": "azul"}),
        ("POST", f"{base}/taxonomy/{uuid.uuid4()}/deactivate", {}),
        ("GET", f"{base}/taxonomy-grants", None),
        ("POST", f"{base}/taxonomy-grants", {"user_id": str(uuid.uuid4())}),
        ("DELETE", f"{base}/taxonomy-grants/{uuid.uuid4()}", {}),
    ]
    for method, url, payload in calls:
        resp = client.request(method, url, json=payload)
        assert resp.status_code == 401, (url, resp.text)


def test_read_is_for_members_and_include_inactive_requires_manage(
    client: TestClient, session_factory
) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
    owner_h = _auth(client, "owner@r.dev")
    member_h = _auth(client, "member@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], member.id)
    _create_value(client, owner_h, ws["id"])

    resp = client.get(f"/workspaces/{ws['id']}/management/taxonomy?kind=category", headers=member_h)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert "senha_hash" not in resp.text

    denied = client.get(
        f"/workspaces/{ws['id']}/management/taxonomy?kind=category&include_inactive=true",
        headers=member_h,
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error_code"] == "TAXONOMY_ACCESS_DENIED"

    allowed = client.get(
        f"/workspaces/{ws['id']}/management/taxonomy?kind=category&include_inactive=true",
        headers=owner_h,
    )
    assert allowed.status_code == 200, allowed.text


def test_capability_denial_is_identical_for_any_target(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
    make_user(session_factory, email="stranger@r.dev", cpf=VALID_CPFS[2])
    owner_h = _auth(client, "owner@r.dev")
    stranger_h = _auth(client, "stranger@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], member.id)
    item = _create_value(client, owner_h, ws["id"])
    base = f"/workspaces/{ws['id']}/management"

    targets = [item["id"], str(uuid.uuid4()), "nao-e-uuid"]
    patch_errors = []
    for target in targets:
        resp = client.patch(f"{base}/taxonomy/{target}", json={"color": "azul"}, headers=stranger_h)
        assert resp.status_code == 403, resp.text
        patch_errors.append(_error(resp.json()))
    assert len(set(patch_errors)) == 1

    grant_errors = []
    for target in [member.id, str(uuid.uuid4()), str(uuid.uuid4())]:
        resp = client.post(f"{base}/taxonomy-grants", json={"user_id": target}, headers=stranger_h)
        assert resp.status_code == 403, resp.text
        grant_errors.append(_error(resp.json()))
    assert len(set(grant_errors)) == 1

    revoke_errors = []
    for target in [member.id, str(uuid.uuid4()), str(uuid.uuid4())]:
        resp = _send(client, "DELETE", f"{base}/taxonomy-grants/{target}", {}, stranger_h)
        assert resp.status_code == 403, resp.text
        revoke_errors.append(_error(resp.json()))
    assert len(set(revoke_errors)) == 1


def test_single_404_for_unknown_and_foreign_targets(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
    stranger = make_user(session_factory, email="stranger@r.dev", cpf=VALID_CPFS[2])
    owner_h = _auth(client, "owner@r.dev")
    ws1 = _workspace(client, owner_h)
    ws2 = _workspace(client, owner_h)
    _add_member(client, owner_h, ws1["id"], member.id)
    foreign_item = _create_value(client, owner_h, ws2["id"], name="Estranho")
    base = f"/workspaces/{ws1['id']}/management"

    results = []
    results.append(
        client.patch(f"{base}/taxonomy/{uuid.uuid4()}", json={"color": "azul"}, headers=owner_h)
    )
    results.append(
        client.patch(
            f"{base}/taxonomy/{foreign_item['id']}", json={"color": "azul"}, headers=owner_h
        )
    )
    results.append(
        client.post(f"{base}/taxonomy/{uuid.uuid4()}/deactivate", json={}, headers=owner_h)
    )
    results.append(
        client.post(f"{base}/taxonomy-grants", json={"user_id": stranger.id}, headers=owner_h)
    )
    results.append(_send(client, "DELETE", f"{base}/taxonomy-grants/{stranger.id}", {}, owner_h))
    results.append(_send(client, "DELETE", f"{base}/taxonomy-grants/{uuid.uuid4()}", {}, owner_h))
    for resp in results:
        assert resp.status_code == 404, resp.text
    assert len({_error(resp.json()) for resp in results}) == 1
    assert results[0].json()["error_code"] == "TAXONOMY_NOT_FOUND"


def test_payload_validation_and_injection_are_rejected(client: TestClient, session_factory) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    headers = _auth(client, "owner@r.dev")
    ws = _workspace(client, headers)
    item = _create_value(client, headers, ws["id"])
    base = f"/workspaces/{ws['id']}/management"

    bad_payloads = [
        ("post", f"{base}/taxonomy", {"kind": "category", "name": "Bug", "workspace_id": ws["id"]}),
        ("post", f"{base}/taxonomy", {"kind": "category; DROP TABLE card_taxonomy", "name": "Bug"}),
        ("post", f"{base}/taxonomy", {"kind": "category", "name": "a" * 101}),
        ("post", f"{base}/taxonomy", {"kind": "category", "name": "<script>x</script>"}),
        ("post", f"{base}/taxonomy", {"kind": "category", "name": "Bug", "color": "<script>"}),
        ("post", f"{base}/taxonomy", {"kind": "category", "name": 123}),
        ("patch", f"{base}/taxonomy/{item['id']}", {"color": "azul", "name": "Novo"}),
        ("patch", f"{base}/taxonomy/{item['id']}", {"color": "x" * 21}),
        ("post", f"{base}/taxonomy/{item['id']}/deactivate", {"reason": "r" * 501}),
        ("post", f"{base}/taxonomy-grants", {"user_id": "nao-e-uuid"}),
        ("post", f"{base}/taxonomy-grants", {"user_id": str(uuid.uuid4()), "level": "grant"}),
        ("delete", f"{base}/taxonomy-grants/{uuid.uuid4()}", {"reason": "r" * 501}),
    ]
    for method, url, payload in bad_payloads:
        resp = _send(client, method, url, payload, headers)
        assert resp.status_code == 422, (method, url, resp.text)

    sqlish = client.post(
        f"{base}/taxonomy",
        json={"kind": "version", "name": "v1' OR '1'='1"},
        headers=headers,
    )
    assert sqlish.status_code == 201, sqlish.text
    assert "senha_hash" not in sqlish.text

    with session_factory() as db:
        assert db.scalar(
            select(CardTaxonomyModel.id).where(CardTaxonomyModel.name == "v1' OR '1'='1")
        )


def test_create_patch_deactivate_reuse_name_and_redacted_audit(
    client: TestClient, session_factory
) -> None:
    owner = make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    headers = _auth(client, "owner@r.dev")
    ws = _workspace(client, headers)
    base = f"/workspaces/{ws['id']}/management"

    with session_factory() as db:
        version_before = db.get(Workspace, ws["id"]).management_permission_version

    created = client.post(
        f"{base}/taxonomy",
        json={
            "kind": "category",
            "name": "  Bug  ",
            "color": "#123456",
        },
        headers={**headers, "x-request-id": "req-" + "y" * 150},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Bug"
    assert "deactivate_reason" not in body
    assert "senha_hash" not in body
    item_id = body["id"]

    patched = client.patch(f"{base}/taxonomy/{item_id}", json={"color": "azul"}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["color"] == "azul"
    assert patched.json()["name"] == "Bug"

    deactivated = client.post(
        f"{base}/taxonomy/{item_id}/deactivate",
        json={"reason": SENSITIVE_REASON},
        headers=headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["desativado_em"] is not None

    active = client.get(f"{base}/taxonomy?kind=category", headers=headers)
    assert active.status_code == 200, active.text
    assert item_id not in [row["id"] for row in active.json()]
    inactive = client.get(f"{base}/taxonomy?kind=category&include_inactive=true", headers=headers)
    assert item_id in [row["id"] for row in inactive.json()]

    reused = client.post(
        f"{base}/taxonomy", json={"kind": "category", "name": "Bug"}, headers=headers
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["id"] != item_id

    with session_factory() as db:
        item = db.get(CardTaxonomyModel, item_id)
        assert item.deactivate_reason == SENSITIVE_REASON
        assert item.desativado_by_id == owner.id
        version_after = db.get(Workspace, ws["id"]).management_permission_version
    assert version_after == version_before + 4

    events = _audit_rows(session_factory, ws["id"])
    pairs = [(e.action, e.permission_version) for e in events]
    assert len(pairs) == 4
    assert ("taxonomy.created", version_before + 1) in pairs
    assert ("taxonomy.color_changed", version_before + 2) in pairs
    assert ("taxonomy.deactivated", version_before + 3) in pairs
    assert ("taxonomy.created", version_before + 4) in pairs
    allowed_keys = {"created", "color_changed", "deactivated"}
    for event in events:
        assert set(event.after or {}).issubset(allowed_keys)
        assert all(isinstance(value, bool) for value in (event.after or {}).values())
        assert event.before is None and event.metadata_ is None
        assert len(event.request_id or "") <= 100
    blob = json.dumps(
        [
            {
                "action": e.action,
                "after": e.after,
                "before": e.before,
                "metadata": e.metadata_,
                "request_id": e.request_id,
            }
            for e in events
        ]
    )
    for forbidden in AUDIT_FORBIDDEN:
        assert forbidden not in blob


def test_grants_soft_revoke_regrant_and_no_pii(client: TestClient, session_factory) -> None:
    owner = make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
    owner_h = _auth(client, "owner@r.dev")
    member_h = _auth(client, "member@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], member.id)
    base = f"/workspaces/{ws['id']}/management"

    granted = client.post(
        f"{base}/taxonomy-grants",
        json={"user_id": member.id, "reason": SENSITIVE_REASON},
        headers=owner_h,
    )
    assert granted.status_code == 201, granted.text
    assert "reason" not in granted.json()
    grant_id = granted.json()["id"]

    listed = client.get(f"{base}/taxonomy-grants", headers=owner_h)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [grant_id]
    assert "reason" not in listed.text and "senha_hash" not in listed.text

    duplicate = client.post(f"{base}/taxonomy-grants", json={"user_id": member.id}, headers=owner_h)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error_code"] == "TAXONOMY_GRANT_ALREADY_ACTIVE"

    member_write = client.post(
        f"{base}/taxonomy", json={"kind": "version", "name": "v-grant"}, headers=member_h
    )
    assert member_write.status_code == 201, member_write.text
    member_delegate = client.post(
        f"{base}/taxonomy-grants", json={"user_id": owner.id}, headers=member_h
    )
    assert member_delegate.status_code == 403, member_delegate.text
    assert member_delegate.json()["error_code"] == "TAXONOMY_GRANT_DENIED"

    revoked = _send(
        client,
        "DELETE",
        f"{base}/taxonomy-grants/{member.id}",
        {"reason": SENSITIVE_REASON},
        owner_h,
    )
    assert revoked.status_code == 204, revoked.text
    with session_factory() as db:
        row = db.get(WorkspaceTaxonomyGrantModel, grant_id)
        assert row.revoked_at is not None
        assert row.revoked_by_id == owner.id
        assert row.revoke_reason == SENSITIVE_REASON
        assert row.updated_at is not None
        assert db.scalar(select(CardTaxonomyModel.id).where(CardTaxonomyModel.name == "v-grant"))

    denied_after_revoke = client.post(
        f"{base}/taxonomy", json={"kind": "version", "name": "v-after"}, headers=member_h
    )
    assert denied_after_revoke.status_code == 403, denied_after_revoke.text

    regranted = client.post(f"{base}/taxonomy-grants", json={"user_id": member.id}, headers=owner_h)
    assert regranted.status_code == 201, regranted.text
    assert regranted.json()["id"] != grant_id

    events = [
        e for e in _audit_rows(session_factory, ws["id"]) if e.action.startswith("taxonomy.grant.")
    ]
    actions = [e.action for e in events]
    assert actions.count("taxonomy.grant.created") == 2
    assert actions.count("taxonomy.grant.revoked") == 1
    for event in events:
        assert set(event.after or {}).issubset({"granted", "revoked"})
        assert all(isinstance(value, bool) for value in (event.after or {}).values())
    blob = json.dumps([{"after": e.after, "metadata": e.metadata_} for e in events])
    assert SENSITIVE_REASON not in blob


def test_internal_admin_break_glass_is_required_and_redacted(
    client: TestClient, session_factory
) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    make_user(session_factory, email="adm@r.dev", cpf=VALID_CPFS[1], admin=True)
    owner_h = _auth(client, "owner@r.dev")
    adm_h = _auth(client, "adm@r.dev")
    ws = _workspace(client, owner_h)
    base = f"/workspaces/{ws['id']}/management"

    missing = client.post(
        f"{base}/taxonomy", json={"kind": "category", "name": "Adm"}, headers=adm_h
    )
    assert missing.status_code == 403, missing.text
    assert missing.json()["error_code"] == "BREAK_GLASS_REASON_REQUIRED"

    allowed = client.post(
        f"{base}/taxonomy",
        json={"kind": "category", "name": "Adm"},
        headers={**adm_h, "x-break-glass-reason": SENSITIVE_REASON},
    )
    assert allowed.status_code == 201, allowed.text

    actions = [e.action for e in _audit_rows(session_factory, ws["id"])]
    assert set(actions) == {"break_glass", "taxonomy.created"}
    blob = json.dumps(
        [
            {"after": e.after, "metadata": e.metadata_}
            for e in _audit_rows(session_factory, ws["id"])
        ]
    )
    assert SENSITIVE_REASON not in blob


def test_capabilities_are_exposed_in_context_and_access(
    client: TestClient, session_factory
) -> None:
    make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    member = make_user(session_factory, email="member@r.dev", cpf=VALID_CPFS[1])
    owner_h = _auth(client, "owner@r.dev")
    member_h = _auth(client, "member@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], member.id)

    def caps(headers: dict[str, str]) -> dict:
        resp = client.get("/me/context", headers=headers)
        assert resp.status_code == 200, resp.text
        found = [w for w in resp.json()["workspaces"] if w["id"] == ws["id"]]
        assert len(found) == 1
        return found[0]["capabilities"]

    owner_caps = caps(owner_h)
    assert owner_caps["taxonomy_read"] is True
    assert owner_caps["taxonomy_manage"] is True
    assert owner_caps["taxonomy_manage_grant"] is True

    member_caps = caps(member_h)
    assert member_caps["taxonomy_read"] is True
    assert member_caps["taxonomy_manage"] is False
    assert member_caps["taxonomy_manage_grant"] is False

    access = client.get(f"/workspaces/{ws['id']}/management/access/me", headers=member_h)
    assert access.status_code == 200, access.text
    assert access.json()["capabilities"]["taxonomy_read"] is True


def test_workspace_owner_without_org_owner_role_can_grant_and_revoke(
    client: TestClient, session_factory
) -> None:
    owner = make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    promoted = make_user(session_factory, email="promoted@r.dev", cpf=VALID_CPFS[1])
    owner_h = _auth(client, "owner@r.dev")
    promoted_h = _auth(client, "promoted@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], promoted.id)
    organization_id = _workspace_organization_id(session_factory, ws["id"])
    _set_organization_role(session_factory, organization_id, promoted.id, "admin")

    transferred = client.patch(
        f"/workspaces/{ws['id']}/members/{promoted.id}",
        json={"role": "owner"},
        headers=owner_h,
    )
    assert transferred.status_code == 200, transferred.text

    context = client.get("/me/context", headers=promoted_h)
    assert context.status_code == 200, context.text
    found = [w for w in context.json()["workspaces"] if w["id"] == ws["id"]]
    assert len(found) == 1
    capabilities = found[0]["capabilities"]
    assert capabilities["taxonomy_read"] is True
    assert capabilities["taxonomy_manage"] is True
    assert capabilities["taxonomy_manage_grant"] is True

    base = f"/workspaces/{ws['id']}/management"
    granted = client.post(f"{base}/taxonomy-grants", json={"user_id": owner.id}, headers=promoted_h)
    assert granted.status_code == 201, granted.text
    assert granted.json()["user_id"] == owner.id

    revoked = _send(client, "DELETE", f"{base}/taxonomy-grants/{owner.id}", {}, promoted_h)
    assert revoked.status_code == 204, revoked.text


def test_active_taxonomy_grant_does_not_delegate_grant_authority(
    client: TestClient, session_factory
) -> None:
    owner = make_user(session_factory, email="owner@r.dev", cpf=VALID_CPFS[0])
    holder = make_user(session_factory, email="holder@r.dev", cpf=VALID_CPFS[1])
    owner_h = _auth(client, "owner@r.dev")
    holder_h = _auth(client, "holder@r.dev")
    ws = _workspace(client, owner_h)
    _add_member(client, owner_h, ws["id"], holder.id)
    organization_id = _workspace_organization_id(session_factory, ws["id"])
    _set_organization_role(session_factory, organization_id, holder.id, "member")

    base = f"/workspaces/{ws['id']}/management"
    granted = client.post(f"{base}/taxonomy-grants", json={"user_id": holder.id}, headers=owner_h)
    assert granted.status_code == 201, granted.text

    context = client.get("/me/context", headers=holder_h)
    assert context.status_code == 200, context.text
    found = [w for w in context.json()["workspaces"] if w["id"] == ws["id"]]
    assert len(found) == 1
    capabilities = found[0]["capabilities"]
    assert capabilities["taxonomy_manage"] is True
    assert capabilities["taxonomy_manage_grant"] is False

    delegated = client.post(f"{base}/taxonomy-grants", json={"user_id": owner.id}, headers=holder_h)
    assert delegated.status_code == 403, delegated.text
    assert delegated.json()["error_code"] == "TAXONOMY_GRANT_DENIED"

    revoked = _send(client, "DELETE", f"{base}/taxonomy-grants/{holder.id}", {}, holder_h)
    assert revoked.status_code == 403, revoked.text
    assert revoked.json()["error_code"] == "TAXONOMY_GRANT_DENIED"
