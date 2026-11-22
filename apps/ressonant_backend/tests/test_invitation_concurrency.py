from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Only run against real Postgres. SQLite cannot validate row locking/concurrency.
def _load_pg_url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql"):
        return url
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        vals = {}
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
        u = vals.get("POSTGRES_USER")
        p = vals.get("POSTGRES_PASSWORD")
        d = vals.get("POSTGRES_DB", "ressonant")
        port = vals.get("POSTGRES_PORT", "5432")
        if u and p:
            return f"postgresql+psycopg2://{u}:{p}@127.0.0.1:{port}/{d}"
    return url


PG_URL = _load_pg_url()
if not PG_URL.startswith("postgresql"):
    pytest.skip("TEST_DATABASE_URL/DATABASE_URL Postgres required", allow_module_level=True)

os.environ.setdefault("AUTH_SECRET", "test-secret-with-at-least-32-characters!!")

from app.common.security import hash_password  # noqa: E402
from app.database.engine import Base  # noqa: E402
from app.modules.billing.domain.models import Plan, Subscription  # noqa: E402
from app.modules.organization.dataproviders.repository import OrganizationRepository  # noqa: E402
from app.modules.organization.domain.models import (  # noqa: E402
    Organization,
    OrganizationMember,
)
from app.modules.organization.schemas.dto import InvitationCreateRequest  # noqa: E402
from app.modules.organization.usecases.services import InvitationService  # noqa: E402
from app.modules.user.domain.models import User  # noqa: E402
from app.modules.workspace.domain.models import Workspace, WorkspaceMember  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    from urllib.parse import urlparse

    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    parsed = urlparse(PG_URL.replace("+psycopg2", ""))
    admin_db = "postgres"
    test_db = f"ressonant_invtest_{uuid.uuid4().hex[:8]}"
    admin_conn = psycopg2.connect(
        dbname=admin_db,
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
    )
    admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with admin_conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{test_db}"')
    admin_conn.close()

    test_url = PG_URL.rsplit("/", 1)[0] + f"/{test_db}"
    engine = create_engine(test_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        admin_conn = psycopg2.connect(
            dbname=admin_db,
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
        )
        admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with admin_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid <> pg_backend_pid()",
                (test_db,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
        admin_conn.close()


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


def _cleanup(session_factory, ids: dict[str, str]) -> None:
    with session_factory() as db:
        # children first; audit/outbox may reference invitation/org.
        db.execute(
            text("DELETE FROM audit_events WHERE organization_id = :org"), {"org": ids["org_id"]}
        )
        db.execute(
            text("DELETE FROM email_outbox WHERE recipient_email LIKE :pat"),
            {"pat": f"%{ids['suffix']}%"},
        )
        db.execute(
            text("DELETE FROM invitations WHERE organization_id = :org"), {"org": ids["org_id"]}
        )
        db.execute(
            text("DELETE FROM workspace_members WHERE workspace_id = :ws"), {"ws": ids["ws_id"]}
        )
        db.execute(text("DELETE FROM workspaces WHERE id = :ws"), {"ws": ids["ws_id"]})
        db.execute(
            text("DELETE FROM organization_members WHERE organization_id = :org"),
            {"org": ids["org_id"]},
        )
        db.execute(
            text("DELETE FROM subscriptions WHERE organization_id = :org"), {"org": ids["org_id"]}
        )
        db.execute(text("DELETE FROM organizations WHERE id = :org"), {"org": ids["org_id"]})
        db.execute(text("DELETE FROM plans WHERE id = :plan"), {"plan": ids["plan_id"]})
        for uid in ids["user_ids"]:
            db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        db.commit()


def _seed(session_factory, *, seat_limit=1, seats_purchased=0, invitees=2):
    suffix = uuid.uuid4().hex[:10]
    org_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    invitee_ids = [str(uuid.uuid4()) for _ in range(invitees)]
    now = datetime.now(UTC)

    with session_factory() as db:
        owner = User(
            id=owner_id,
            email=f"owner-{suffix}@example.com",
            senha_hash=hash_password("senha-forte-1"),
            cpf=str(10000000000 + uuid.uuid4().int % 89999999999),
            telefone="11999990000",
            idade=30,
            termos_contrato=True,
            status_ativo=True,
        )
        db.add(owner)
        for i, uid in enumerate(invitee_ids):
            db.add(
                User(
                    id=uid,
                    email=f"invitee-{i}-{suffix}@example.com",
                    senha_hash=hash_password("senha-forte-1"),
                    cpf=str(10000000000 + uuid.uuid4().int % 89999999999),
                    telefone="11999990001",
                    idade=30,
                    termos_contrato=True,
                    status_ativo=True,
                )
            )
        db.add(Organization(id=org_id, name=f"Org {suffix}", slug=f"org-{suffix}"))
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=org_id, user_id=owner_id, role="owner", status="active"
            )
        )
        db.add(
            Workspace(
                id=ws_id,
                name=f"WS {suffix}",
                slug=f"ws-{suffix}",
                owner_id=owner_id,
                organization_id=org_id,
            )
        )
        db.add(WorkspaceMember(workspace_id=ws_id, user_id=owner_id, role="admin"))
        db.add(
            Plan(
                id=plan_id,
                code=f"plan-{suffix}",
                name="Plan",
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
                status="active",
                seats_purchased=seats_purchased,
            )
        )
        db.commit()

    return {
        "suffix": suffix,
        "org_id": org_id,
        "ws_id": ws_id,
        "plan_id": plan_id,
        "owner_id": owner_id,
        "user_ids": [owner_id, *invitee_ids],
        "invitee_ids": invitee_ids,
        "now": now,
    }


def test_concurrent_accept_does_not_exceed_seat_limit(session_factory):
    ids = _seed(session_factory, seat_limit=1, invitees=2)
    try:
        with session_factory() as db:
            # temporarily allow creating 2 pending invites
            plan = db.get(Plan, ids["plan_id"])
            plan.seat_limit = 3
            db.commit()
        with session_factory() as db:
            owner = db.get(User, ids["owner_id"])
            svc = InvitationService(OrganizationRepository(db))
            inv1 = svc.create_invitation(
                ids["org_id"],
                owner,
                InvitationCreateRequest(
                    email=f"invitee-0-{ids['suffix']}@example.com",
                    role="member",
                    workspace_id=ids["ws_id"],
                ),
            )
            inv2 = svc.create_invitation(
                ids["org_id"],
                owner,
                InvitationCreateRequest(
                    email=f"invitee-1-{ids['suffix']}@example.com",
                    role="member",
                    workspace_id=ids["ws_id"],
                ),
            )
            token1, token2 = inv1.token, inv2.token
        with session_factory() as db:
            plan = db.get(Plan, ids["plan_id"])
            plan.seat_limit = 2  # owner uses 1, only 1 slot left
            db.commit()

        barrier = threading.Barrier(2)
        results: list[tuple[str, int | str]] = []
        lock = threading.Lock()

        def accept(token: str, user_id: str):
            with session_factory() as db:
                user = db.get(User, user_id)
                svc = InvitationService(OrganizationRepository(db))
                barrier.wait(timeout=10)
                try:
                    resp = svc.accept_invitation(token, user)
                    with lock:
                        results.append(("ok", resp.status))
                except Exception as exc:  # noqa: BLE001
                    code = (
                        getattr(getattr(exc, "exception_data", None), "error_code", None)
                        or getattr(exc, "error_code", None)
                        or exc.__class__.__name__
                    )
                    with lock:
                        results.append(("err", f"{code}:{exc}"))

        t1 = threading.Thread(target=accept, args=(token1, ids["invitee_ids"][0]))
        t2 = threading.Thread(target=accept, args=(token2, ids["invitee_ids"][1]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        ok = [r for r in results if r[0] == "ok"]
        err = [r for r in results if r[0] == "err"]
        assert len(ok) == 1
        assert len(err) == 1
        assert err[0][1].startswith("SEAT_LIMIT_EXCEEDED")

        with session_factory() as db:
            members = (
                db.query(OrganizationMember)
                .filter(
                    OrganizationMember.organization_id == ids["org_id"],
                    OrganizationMember.status == "active",
                )
                .all()
            )
            assert len(members) == 2  # owner + one accepted invitee
    finally:
        _cleanup(session_factory, ids)


def test_concurrent_register_invited_user_does_not_exceed_seat_limit(session_factory):
    ids = _seed(session_factory, seat_limit=1, invitees=2)
    try:
        # create invites for emails that do not yet have accounts
        emails = [f"new-{i}-{ids['suffix']}@example.com" for i in range(2)]
        with session_factory() as db:
            plan = db.get(Plan, ids["plan_id"])
            plan.seat_limit = 3
            db.commit()
        with session_factory() as db:
            owner = db.get(User, ids["owner_id"])
            svc = InvitationService(OrganizationRepository(db))
            tokens = []
            for email in emails:
                inv = svc.create_invitation(
                    ids["org_id"],
                    owner,
                    InvitationCreateRequest(email=email, role="member", workspace_id=ids["ws_id"]),
                )
                tokens.append(inv.token)
        with session_factory() as db:
            plan = db.get(Plan, ids["plan_id"])
            plan.seat_limit = 2  # owner uses 1, only 1 slot left
            db.commit()

        from app.modules.auth.schemas.dto import InviteRegistrationCreate
        from app.modules.auth.usecases.registration import RegistrationService

        barrier = threading.Barrier(2)
        results: list[tuple[str, str]] = []
        lock = threading.Lock()

        def register(token: str, cpf_suffix: int):
            payload = InviteRegistrationCreate(
                token=token,
                nome_completo=f"User {cpf_suffix} Test",
                cpf=f"{10000000000 + cpf_suffix:011d}"[-11:],
                telefone="11999990002",
                senha="senha-forte-1",
                idade=25,
                termos_contrato=True,
            )
            with session_factory() as db:
                svc = RegistrationService(db)
                barrier.wait(timeout=10)
                try:
                    user, inv = svc.register_invited_user(payload)
                    with lock:
                        results.append(("ok", user.email))
                except Exception as exc:  # noqa: BLE001
                    code = (
                        getattr(getattr(exc, "exception_data", None), "error_code", None)
                        or getattr(exc, "error_code", None)
                        or exc.__class__.__name__
                    )
                    with lock:
                        results.append(("err", f"{code}:{exc}"))

        threads = [threading.Thread(target=register, args=(tokens[i], 1000 + i)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 2
        ok = [r for r in results if r[0] == "ok"]
        err = [r for r in results if r[0] == "err"]
        assert len(ok) == 1, results
        assert len(err) == 1, results
        assert err[0][1].startswith("SEAT_LIMIT_EXCEEDED"), results

        with session_factory() as db:
            active_members = (
                db.query(OrganizationMember)
                .filter(
                    OrganizationMember.organization_id == ids["org_id"],
                    OrganizationMember.status == "active",
                )
                .count()
            )
            assert active_members == 2  # owner + 1
    finally:
        _cleanup(session_factory, ids)
