"""Regressões dos achados CYB-001..004 do parecer pré-frontend."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from app.common.security import hash_password
from app.modules.auth.usecases.tokens import decode_access_token
from app.modules.billing.domain.models import Plan, Subscription
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.models import Invitation, Organization, OrganizationMember
from app.modules.teams.domain.models import Team
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from common.errors import setup_exception_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.conftest import VALID_CPFS, login


def _seed_context(session_factory, *, suffix: str | None = None) -> dict[str, str]:
    """Organização com owner, workspace e time — base para os cenários de convite."""
    suffix = suffix or uuid.uuid4().hex[:10]
    with session_factory() as db:
        org = Organization(
            name=f"Org {suffix}", slug=f"org-{suffix}", corporate_domain="example.com"
        )
        db.add(org)
        db.flush()
        owner_email = f"owner-{suffix}@x.com"
        owner = User(
            email=owner_email,
            senha_hash=hash_password("senha-forte-1"),
            cpf=str(10000000000 + (uuid.uuid4().int % 89999999999)),
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
        team = Team(
            name=f"Equipe {suffix}",
            slug=f"equipe-{suffix}",
            owner_id=owner.id,
            workspace_id=ws.id,
            key_prefix="TST",
        )
        db.add(team)
        plan = Plan(
            code=f"p-{suffix}",
            name=f"P {suffix}",
            price_cents=0,
            currency="BRL",
            seat_limit=10,
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
        return {
            "org_id": org.id,
            "ws_id": ws.id,
            "team_id": team.id,
            "owner_email": owner_email,
        }


def _add_invitation(
    session_factory,
    ctx: dict[str, str],
    *,
    personal_email: str,
    corporate_email: str,
    cpf: str | None = None,
    team_id: str | None = None,
) -> str:
    """Insere convite com token em claro para devolver ao chamador (teste only)."""
    token = uuid.uuid4().hex
    with session_factory() as db:
        if cpf:
            db.add(User(email=f"existing-{uuid.uuid4().hex[:8]}@x.com", senha_hash="x", cpf=cpf))
            db.flush()
        invitation = Invitation(
            organization_id=ctx["org_id"],
            workspace_id=ctx["ws_id"],
            personal_email=personal_email,
            corporate_email=corporate_email,
            invitee_name="Helena Rocha",
            team_id=team_id,
            role="member",
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(days=7),
            invited_by_id=db.scalar(
                select(OrganizationMember.user_id).where(
                    OrganizationMember.organization_id == ctx["org_id"]
                )
            ),
            send_status="pending",
            reservation_active=True,
        )
        db.add(invitation)
        db.commit()
        return token


def _seed_default_plans(session_factory) -> None:
    """Evita o seed concorrente do fixture client durante o teste paralelo."""
    with session_factory() as db:
        existing = {code for (code,) in db.execute(select(Plan.code)).all()}
        defaults = (
            ("inicial", "Inicial", 0, 3, 7),
            ("equipe", "Equipe", 4900, 15, 14),
            ("empresa", "Empresa", 7900, None, 14),
        )
        pending = [
            Plan(
                code=code,
                name=name,
                price_cents=price,
                currency="BRL",
                seat_limit=seat,
                trial_days=days,
                active=True,
            )
            for code, name, price, seat, days in defaults
            if code not in existing
        ]
        if pending:
            db.add_all(pending)
            db.commit()


def _accept_payload(token: str, cpf: str) -> dict[str, object]:
    return {
        "token": token,
        "nome_completo": "Helena Rocha",
        "cpf": cpf,
        "senha": "senha-forte-1",
        "termos_contrato": True,
    }


def test_cyb002_foreign_team_id_is_rejected_with_422(client, session_factory):
    own = _seed_context(session_factory)
    foreign = _seed_context(session_factory)
    headers = login(client, own["owner_email"], "senha-forte-1")

    response = client.post(
        f"/organizations/{own['org_id']}/invitations",
        json={
            "email": "convidado@example.com",
            "nome_completo": "Convidado Exemplo",
            "role": "member",
            "workspace_id": own["ws_id"],
            "team_id": foreign["team_id"],
        },
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "INVALID_TEAM"
    with session_factory() as db:
        alheios = db.scalar(
            select(func.count(Invitation.id))
            .join(Team, Invitation.team_id == Team.id)
            .join(Workspace, Team.workspace_id == Workspace.id)
            .where(Workspace.organization_id != Invitation.organization_id)
        )
    assert alheios == 0


def test_cyb002_foreign_team_name_is_not_leaked_on_list_or_public_read(client, session_factory):
    own = _seed_context(session_factory)
    foreign = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        own,
        personal_email="convidado@example.com",
        corporate_email="convidado.corp@example.com",
        team_id=foreign["team_id"],
    )
    headers = login(client, own["owner_email"], "senha-forte-1")

    listing = client.get(f"/organizations/{own['org_id']}/invitations", headers=headers)
    assert listing.status_code == 200, listing.text
    rows = [row for row in listing.json() if row["corporate_email"] == "convidado.corp@example.com"]
    assert len(rows) == 1
    assert rows[0]["team_name"] is None

    public = client.get(f"/invitations/{token}")
    assert public.status_code == 200, public.text
    assert public.json()["team_name"] is None


def test_cyb003_valid_accept_returns_201_with_usable_token(client, session_factory):
    ctx = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        ctx,
        personal_email="helena.pessoal@example.com",
        corporate_email="helena.rocha@example.com",
        team_id=ctx["team_id"],
    )

    response = client.post("/auth/register/invitation", json=_accept_payload(token, VALID_CPFS[0]))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["workspace_id"] == ctx["ws_id"]
    assert body["organization_id"] == ctx["org_id"]
    assert "senha_hash" not in body["user"]
    assert body["user"]["email"] == "helena.rocha@example.com"
    assert body["user"]["telefone"] is None
    assert body["user"]["idade"] is None

    # O token precisa ser decodificável pela própria app e apontar para o
    # usuário recém-criado; /me/context usa UserResponse (contrato legado,
    # fora do escopo BE-03) e não é a prova deste critério.
    user_id = decode_access_token(body["access_token"])
    assert user_id is not None
    with session_factory() as db:
        created = db.scalar(select(User.id).where(User.email == "helena.rocha@example.com"))
    assert created == user_id


def test_cyb004_duplicate_cpf_returns_409_not_500(client, session_factory):
    ctx = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        ctx,
        personal_email="dup.pessoal@example.com",
        corporate_email="dup.corp@example.com",
        cpf=VALID_CPFS[1],
    )

    response = client.post("/auth/register/invitation", json=_accept_payload(token, VALID_CPFS[1]))

    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "USER_ALREADY_EXISTS"


def test_cyb004_second_accept_is_serialized_and_never_returns_500(
    client, session_factory, monkeypatch
):
    """A 2ª requisição espera o lock da linha do convite e vê `accepted_at`.

    O paralelismo com TestClient/SQLite é instável (a sessão é compartilhada
    entre threads e não há FOR UPDATE); a concorrência real em Postgres é
    verificada pelo critério objetivo CYB-004 contra a API no Docker. Aqui
    provamos as duas partes verificáveis em unitário: o lock é pedido em todo
    aceite e o estado pós-commit barra o segundo com 409 de domínio.
    """
    _seed_default_plans(session_factory)
    ctx = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        ctx,
        personal_email="race.pessoal@example.com",
        corporate_email="race.corp@example.com",
    )

    lock_calls: list[bool] = []
    original = OrganizationRepository.get_invitation_by_token_hash

    def spy(self, token_hash: str, *, for_update: bool = False):
        lock_calls.append(for_update)
        return original(self, token_hash, for_update=for_update)

    monkeypatch.setattr(OrganizationRepository, "get_invitation_by_token_hash", spy)

    first = client.post("/auth/register/invitation", json=_accept_payload(token, VALID_CPFS[2]))
    second = client.post("/auth/register/invitation", json=_accept_payload(token, VALID_CPFS[3]))

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error_code"] == "INVITATION_ALREADY_USED"
    assert lock_calls == [True, True], lock_calls
    with session_factory() as db:
        accepted = db.scalar(
            select(Invitation.accepted_at).where(
                Invitation.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
            )
        )
        users = db.scalar(select(func.count(User.id)).where(User.email == "race.corp@example.com"))
    assert accepted is not None
    assert users == 1


def test_cyb001_general_handler_logs_no_pii(caplog, capsys):
    caplog.set_level("ERROR")
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        error = Exception(
            "duplicate key users_cpf_key Key (cpf)=(52998224725) "
            "$argon2id$v=19$m=65536 helena@example.com"
        )
        diag = type("Diag", (), {"constraint_name": "users_cpf_key"})()
        error.orig = type("Orig", (), {"diag": diag})()
        raise error

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error_code"] == "UNEXPECTED_ERROR"
    output = caplog.text + capsys.readouterr().out
    for secret in ("52998224725", "$argon2id$", "helena@example.com"):
        assert secret not in output
    assert "users_cpf_key" in output
