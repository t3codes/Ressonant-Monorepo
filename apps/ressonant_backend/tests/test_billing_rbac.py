from __future__ import annotations

import socket
import uuid
from unittest.mock import patch

import pytest
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.domain.models import TeamMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace_management.domain.models import AuditEvent, WorkspaceManagementGrant
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from tests.conftest import login, make_user

CPFS = [
    "10433218100",
    "96001338914",
    "08386379499",
    "02654235114",
    "16155940789",
    "81618495950",
    "31034131656",
    "47525534144",
]
CATALOG = (
    ("00000000-0000-0000-0000-000000000001", "inicial", "Inicial", 0, 3, None, 14),
    ("00000000-0000-0000-0000-000000000002", "equipe", "Equipe", 4900, 15, 4900, 14),
    ("00000000-0000-0000-0000-000000000003", "empresa", "Empresa", 7900, None, None, 14),
)


def _seed_catalog(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        db.add_all(
            Plan(
                id=plan_id,
                code=code,
                name=name,
                price_cents=price,
                currency="BRL",
                seat_limit=seat_limit,
                overage_cents_per_seat=overage,
                trial_days=trial_days,
                active=True,
            )
            for plan_id, code, name, price, seat_limit, overage, trial_days in CATALOG
        )
        db.commit()


def _seed_context(
    session_factory: sessionmaker,
    *,
    actor_role: str | None = None,
    actor_admin: bool = False,
    actor_ws_owner: bool = False,
    actor_ws_member: bool = True,
    actor_team_member: bool = True,
    grant_level: str | None = None,
    plan_code: str = "equipe",
    with_subscription: bool = True,
    extra_members: int = 0,
) -> dict:
    """Monta o cenário de cinco eixos com papéis vindos de membership persistida."""
    actor = make_user(
        session_factory,
        email="actor@billing.dev",
        cpf=CPFS[0],
        admin=actor_admin,
    )
    is_org_owner = actor_role in {"org_owner", "owner"}
    db_role = "owner" if is_org_owner else ("admin" if actor_role == "org_admin" else actor_role)
    owner = (
        actor
        if is_org_owner
        else make_user(session_factory, email="owner@billing.dev", cpf=CPFS[1])
    )
    target = make_user(session_factory, email="target@billing.dev", cpf=CPFS[2])
    extras = [
        make_user(session_factory, email=f"extra{index}@billing.dev", cpf=CPFS[3 + index])
        for index in range(extra_members)
    ]

    organization_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    with session_factory() as db:
        db.add(Organization(id=organization_id, name="Acme", slug=f"acme-{uuid.uuid4()}"))
        db.add(
            OrganizationMember(
                organization_id=organization_id,
                user_id=owner.id,
                role="owner",
                status="active",
            )
        )
        if not is_org_owner and db_role in {"billing_owner", "admin", "member"}:
            db.add(
                OrganizationMember(
                    organization_id=organization_id,
                    user_id=actor.id,
                    role=db_role,
                    status="active",
                )
            )
        db.add(
            OrganizationMember(
                organization_id=organization_id,
                user_id=target.id,
                role="member",
                status="active",
            )
        )
        for extra in extras:
            db.add(
                OrganizationMember(
                    organization_id=organization_id,
                    user_id=extra.id,
                    role="member",
                    status="active",
                )
            )

        workspace_owner_id = actor.id if (is_org_owner or actor_ws_owner) else owner.id
        db.add(
            Workspace(
                id=workspace_id,
                name="Acme Workspace",
                slug=f"ws-{uuid.uuid4()}",
                organization_id=organization_id,
                owner_id=workspace_owner_id,
            )
        )
        ws_members: dict[str, str] = {
            owner.id: "admin",
            target.id: "member",
            **{extra.id: "member" for extra in extras},
        }
        if actor_ws_member:
            ws_members[actor.id] = "admin" if actor.id == workspace_owner_id else "member"
        for user_id, role in ws_members.items():
            db.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role))
        if grant_level is not None:
            db.add(
                WorkspaceManagementGrant(
                    workspace_id=workspace_id,
                    user_id=actor.id,
                    level=grant_level,
                    granted_by_id=owner.id,
                )
            )
        if actor_ws_member and actor_team_member:
            pass  # TeamMember é criado depois, via API, junto com o card.
        if with_subscription:
            plan = db.scalar(select(Plan).where(Plan.code == plan_code))
            assert plan is not None
            db.add(
                Subscription(
                    organization_id=organization_id,
                    plan_id=plan.id,
                    status="trialing",
                    seats_purchased=0,
                )
            )
        db.commit()

    return {
        "actor": actor,
        "owner": owner,
        "target": target,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "extras": extras,
    }


def _seed_card(
    client: TestClient, session_factory: sessionmaker, ctx: dict, actor_team_member: bool
) -> dict:
    owner_headers = login(client, ctx["owner"].email)
    suffix = uuid.uuid4().hex[:8]
    team = client.post(
        "/teams",
        json={
            "name": "Engenharia",
            "slug": f"eng-{suffix}",
            "workspace_id": ctx["workspace_id"],
        },
        headers=owner_headers,
    )
    assert team.status_code == 201, team.text
    board = client.post(
        "/boards",
        json={
            "name": "Board",
            "slug": f"board-{suffix}",
            "workspace_id": ctx["workspace_id"],
            "team_id": team.json()["id"],
        },
        headers=owner_headers,
    )
    assert board.status_code == 201, board.text
    card = client.post(
        "/cards",
        json={
            "title": "Cartão de teste",
            "board_id": board.json()["id"],
            "team_id": team.json()["id"],
        },
        headers=owner_headers,
    )
    assert card.status_code == 201, card.text
    if actor_team_member and ctx["actor"].id != ctx["owner"].id:
        with session_factory() as db:
            db.add(
                TeamMember(
                    team_id=team.json()["id"],
                    user_id=ctx["actor"].id,
                    role="member",
                )
            )
            db.commit()
    return {"card": card.json(), "team_id": team.json()["id"]}


def _grant(client: TestClient, headers: dict, ctx: dict, level: str, reason: str | None = None):
    payload = {"user_id": ctx["target"].id, "level": level}
    if reason is not None:
        payload["reason"] = reason
    return client.post(
        f"/workspaces/{ctx['workspace_id']}/management/grants",
        json=payload,
        headers=headers,
    )


def _headers(client: TestClient, ctx: dict, *, reason: str | None = None) -> dict:
    headers = login(client, ctx["actor"].email)
    if reason is not None:
        headers["x-break-glass-reason"] = reason
    return headers


def _count_events(session_factory: sessionmaker, *, action: str | None = None) -> int:
    with session_factory() as db:
        statement = select(AuditEvent)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        return len(list(db.scalars(statement)))


# role, billing GET, billing PATCH, grant grant, grant modify, card write
MATRIX = (
    ("org_owner", 200, 200, 201, 201, True),
    ("billing_owner", 200, 200, 403, 403, False),
    ("org_admin", 403, 403, 403, 201, True),
    ("workspace_owner", 403, 403, 403, 201, True),
    ("grant_grant", 403, 403, 403, 201, True),
    ("grant_modify", 403, 403, 403, 403, True),
    ("grant_read", 403, 403, 403, 403, True),
    ("interno_adm", 200, 200, 201, 201, True),
    ("viewer", 403, 403, 403, 403, False),
)


@pytest.mark.parametrize(
    ("role", "view_status", "patch_status", "grant_status", "modify_status", "card_write"),
    MATRIX,
)
def test_five_axis_matrix_actions(
    client: TestClient,
    session_factory: sessionmaker,
    role: str,
    view_status: int,
    patch_status: int,
    grant_status: int,
    modify_status: int,
    card_write: bool,
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(
        session_factory,
        actor_role=role if role in {"org_owner", "billing_owner", "org_admin"} else None,
        actor_admin=role == "interno_adm",
        actor_ws_owner=role == "workspace_owner",
        actor_ws_member=role != "viewer",
        actor_team_member=card_write,
        grant_level={"grant_grant": "grant", "grant_modify": "modify", "grant_read": "read"}.get(
            role
        ),
    )
    reason = "suporte emergencial" if role == "interno_adm" else None
    headers = _headers(client, ctx, reason=reason)
    org_id = ctx["organization_id"]

    view = client.get(f"/organizations/{org_id}/billing", headers=headers)
    assert view.status_code == view_status, view.text
    if view_status == 403:
        body = view.json()
        assert body["error_code"] == "BILLING_ACCESS_DENIED"
        assert body["error_layer"] == "billing"
        assert body["required_capability"] == "billing.view"
    else:
        assert view.json()["provider"] == "stub"

    patch = client.patch(
        f"/organizations/{org_id}/billing",
        json={"seats_purchased": 1},
        headers=headers,
    )
    assert patch.status_code == patch_status, patch.text
    if patch_status == 403:
        body = patch.json()
        assert body["error_code"] == "BILLING_ACCESS_DENIED"
        assert body["required_capability"] == "billing.manage"

    grant = _grant(client, headers, ctx, "grant", reason=reason)
    assert grant.status_code == grant_status, grant.text
    if grant_status == 403:
        # Quem pode gerenciar grants mas não escalar (R9) recebe o código de escalada;
        # quem sequer pode gerenciar grants recebe ACCESS_DENIED.
        escalates = role in {"org_admin", "workspace_owner", "grant_grant"}
        expected_code = (
            "MANAGEMENT_GRANT_ESCALATION_DENIED" if escalates else "MANAGEMENT_ACCESS_DENIED"
        )
        expected_capability = "management.grant.grant" if escalates else "management.grant"
        assert grant.json()["error_code"] == expected_code
        assert grant.json()["error_layer"] == "management"
        assert grant.json()["required_capability"] == expected_capability

    modify = _grant(client, headers, ctx, "modify", reason=reason)
    assert modify.status_code == modify_status, modify.text
    if modify_status == 403:
        assert modify.json()["error_code"] == "MANAGEMENT_ACCESS_DENIED"
        assert modify.json()["required_capability"] == "management.grant"

    card = _seed_card(client, session_factory, ctx, card_write)["card"]
    update = client.put(
        f"/cards/{card['id']}",
        json={"title": "Cartão atualizado", "expected_version": card["version"]},
        headers=headers,
    )
    assert update.status_code == (200 if card_write else 403), update.text


def test_r9_grant_cannot_escalate_and_audit_only_on_success(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(session_factory, grant_level="grant")
    headers = _headers(client, ctx)
    before = _count_events(session_factory, action="management.grant.upsert")

    denied = _grant(client, headers, ctx, "grant")
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "MANAGEMENT_GRANT_ESCALATION_DENIED"
    assert _count_events(session_factory, action="management.grant.upsert") == before

    owner_headers = login(client, ctx["owner"].email)
    allowed = _grant(client, owner_headers, ctx, "grant")
    assert allowed.status_code == 201, allowed.text
    assert _count_events(session_factory, action="management.grant.upsert") == before + 1


def test_r10_break_glass_reason_and_audit(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(session_factory, actor_admin=True, actor_ws_member=False)
    no_reason = _headers(client, ctx)
    before = _count_events(session_factory)

    denied = _grant(client, no_reason, ctx, "modify")
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "BREAK_GLASS_REASON_REQUIRED"
    assert denied.json()["required_capability"] == "management.break_glass_reason"
    assert _count_events(session_factory) == before

    # `reason` é campo do body na API de gestão, não header.
    allowed = _grant(client, no_reason, ctx, "modify", reason="suporte emergencial")
    assert allowed.status_code == 201, allowed.text
    with session_factory() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "management.grant.upsert"))
    assert event is not None
    assert event.metadata_ is not None
    assert event.metadata_["break_glass"] is True
    assert event.metadata_["reason"] == "suporte emergencial"
    assert event.actor_type == "internal_admin"
    assert _count_events(session_factory) == before + 1


def test_seat_limit_fails_before_commit_without_orphans(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(
        session_factory, actor_role="owner", with_subscription=False, extra_members=2
    )
    headers = _headers(client, ctx)
    org_id = ctx["organization_id"]

    denied = client.post(
        f"/organizations/{org_id}/billing/subscription",
        json={"plan_code": "inicial"},
        headers=headers,
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error_code"] == "SEAT_LIMIT_EXCEEDED"
    assert denied.json()["error_layer"] == "domain"

    with session_factory() as db:
        assert db.get(Organization, org_id) is not None
        assert not list(
            db.scalars(select(Subscription).where(Subscription.organization_id == org_id))
        )
    assert _count_events(session_factory) == 0

    upsized = client.post(
        f"/organizations/{org_id}/billing/subscription",
        json={"plan_code": "inicial", "seats_purchased": 1},
        headers=headers,
    )
    assert upsized.status_code == 201, upsized.text
    assert upsized.json()["subscription"]["seats_purchased"] == 1

    downgrade = client.patch(
        f"/organizations/{org_id}/billing",
        json={"plan_code": "inicial", "seats_purchased": 0},
        headers=headers,
    )
    assert downgrade.status_code == 409
    with session_factory() as db:
        subscription = db.scalar(select(Subscription).where(Subscription.organization_id == org_id))
        assert subscription is not None
        assert subscription.seats_purchased == 1
        plan = db.get(Plan, subscription.plan_id)
        assert plan is not None
        assert plan.code == "inicial"


def test_subscription_lifecycle_uses_no_socket(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(session_factory, actor_role="billing_owner", with_subscription=False)
    headers = _headers(client, ctx)
    org_id = ctx["organization_id"]

    with patch.object(socket, "socket", side_effect=AssertionError("rede não permitida")):
        created = client.post(
            f"/organizations/{org_id}/billing/subscription",
            json={"plan_code": "equipe", "seats_purchased": 2},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["subscription"]["status"] == "trialing"
        assert created.json()["subscription"]["gateway_ref"].startswith("stub_")

        statuses = []
        for status in ("active", "past_due", "active", "canceled"):
            response = client.patch(
                f"/organizations/{org_id}/billing/subscription/status",
                json={"status": status},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            statuses.append(response.json()["subscription"]["status"])

        invalid = client.patch(
            f"/organizations/{org_id}/billing/subscription/status",
            json={"status": "active"},
            headers=headers,
        )
        assert invalid.status_code == 409
        assert invalid.json()["error_code"] == "INVALID_SUBSCRIPTION_TRANSITION"

    assert statuses == ["active", "past_due", "active", "canceled"]
    with session_factory() as db:
        rows = list(db.scalars(select(Subscription).where(Subscription.organization_id == org_id)))
        assert len(rows) == 1
        assert rows[0].status == "canceled"


def test_billing_audit_carries_scope_role_result_and_request_id(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(session_factory, actor_role="billing_owner")
    headers = _headers(client, ctx)
    headers["x-request-id"] = "req-billing-123"
    response = client.patch(
        f"/organizations/{ctx['organization_id']}/billing",
        json={"plan_code": "empresa", "seats_purchased": 4},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    with session_factory() as db:
        events = list(
            db.scalars(
                select(AuditEvent).where(AuditEvent.organization_id == ctx["organization_id"])
            )
        )
    assert len(events) == 1
    event = events[0]
    assert event.scope == "organization"
    assert event.actor_role == "billing_owner"
    assert event.actor_user_id == ctx["actor"].id
    assert event.result == "success"
    assert event.request_id == "req-billing-123"
    assert event.permission_version == 1
    assert event.action == "billing.updated"
    assert event.before == {"plan_code": "equipe", "seats_purchased": 0}
    assert event.after == {"plan_code": "empresa", "seats_purchased": 4}


def test_billing_contract_auth_and_body_validation(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _seed_catalog(session_factory)
    ctx = _seed_context(session_factory, actor_role="owner")
    org_id = ctx["organization_id"]

    assert client.get(f"/organizations/{org_id}/billing").status_code == 401
    headers = _headers(client, ctx)
    denied = client.get(f"/organizations/{uuid.uuid4()}/billing", headers=headers)
    # Sem vínculo, 403 e 404 são indistinguíveis para quem não tem acesso (D5).
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "BILLING_ACCESS_DENIED"
    invalid = client.patch(
        f"/organizations/{org_id}/billing",
        json={"plan_code": "equipe", "actor_role": "owner"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_billing_contract_is_published() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    assert set(paths) >= {
        "/organizations/{organization_id}/billing",
        "/organizations/{organization_id}/billing/subscription",
        "/organizations/{organization_id}/billing/subscription/status",
    }
    assert set(paths["/organizations/{organization_id}/billing"]) == {"get", "patch"}
