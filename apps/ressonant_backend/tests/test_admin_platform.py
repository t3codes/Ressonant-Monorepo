from types import SimpleNamespace

import app.scripts.create_admin as create_admin
import app.scripts.seed_prod_catalog as seed_catalog
import pytest
from app.common.exceptions import ConflictException
from app.modules.auth.usecases.tokens import create_access_token
from app.modules.billing.domain.models import Plan
from app.modules.chat.entrypoints.websocket import _authenticate
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from app.modules.user.usecases.services import UserService
from app.modules.workspace_management.domain.models import AuditEvent
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, login, make_user, register_payload


def test_bootstrap_is_idempotent_and_keeps_password(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        admin_email="root@ressonant.dev",
        admin_password=SecretStr("SenhaForte123!"),
        admin_cpf=VALID_CPFS[0],
        admin_name="Root",
        admin_telefone="11999999999",
    )
    monkeypatch.setattr(create_admin, "get_settings", lambda: settings)
    monkeypatch.setattr(create_admin, "get_session_factory", lambda: session_factory)

    assert create_admin.main() == 0
    with session_factory() as db:
        original_hash = str(db.scalar(select(User.senha_hash)))

    assert create_admin.main() == 0
    with session_factory() as db:
        users = db.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].senha_hash == original_hash
        assert users[0].interno_adm is True
        assert users[0].status_ativo is True


def test_websocket_handshake_rejects_stale_permission_version(
    session_factory: sessionmaker[Session],
) -> None:
    user = make_user(session_factory, email="ws@ressonant.dev", cpf=VALID_CPFS[0])
    token, _ = create_access_token(user.id, permission_version=1)
    with session_factory() as db:
        assert _authenticate(db, token) is not None
        persisted = db.get(User, user.id)
        assert persisted is not None
        persisted.permission_version = 2
        db.commit()
    with session_factory() as db:
        assert _authenticate(db, token) is None
    fresh, _ = create_access_token(user.id, permission_version=2)
    with session_factory() as db:
        assert _authenticate(db, fresh) is not None


def test_platform_admin_guard_blocks_regular_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    make_user(session_factory, email="comum@ressonant.dev", cpf=VALID_CPFS[0])
    response = client.get("/admin/plans", headers=login(client, "comum@ressonant.dev"))
    assert response.status_code == 403
    assert response.json()["error_code"] == "PLATFORM_ADMIN_REQUIRED"


def test_second_superuser_is_audited_and_masks_cpf(
    client: TestClient, session_factory: sessionmaker[Session], admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/admin/superusers",
        json={
            "nome": "Segundo Admin",
            "email": "segundo@ressonant.dev",
            "cpf": VALID_CPFS[1],
            "telefone": "11988887777",
            "password": "SenhaForte123!",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cpf_masked"] == "***.***.***-35"
    assert VALID_CPFS[1] not in response.text
    assert "senha_hash" not in response.text
    assert "password" not in response.text

    with session_factory() as db:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.scope == "system",
                AuditEvent.action == "admin.superuser.created",
            )
        ).all()
        assert len(events) == 1
        assert events[0].actor_type == "internal_admin"
        assert events[0].result == "success"


def test_admin_can_create_plan_with_audited_catalog_change(
    client: TestClient, session_factory: sessionmaker[Session], admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/admin/plans",
        json={
            "code": "plano_novo",
            "name": "Plano Novo",
            "base_price_cents": 9900,
            "included_seats": 5,
            "trial_days": 10,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "plano_novo"
    assert body["price_cents"] == 9900
    assert body["is_active"] is True
    with session_factory() as db:
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.scope == "system", AuditEvent.action == "admin.plan.created"
            )
        )
        assert event is not None
        assert event.entity_type == "plan"


def test_admin_schemas_reject_extra_fields_and_secret_settings(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    extra = client.post(
        "/admin/superusers",
        json={
            "nome": "Extra",
            "email": "extra@ressonant.dev",
            "cpf": VALID_CPFS[1],
            "telefone": "11988887777",
            "password": "SenhaForte123!",
            "senha_hash": "vazamento",
        },
        headers=admin_headers,
    )
    assert extra.status_code == 422

    secret = client.patch(
        "/admin/settings/auth_token",
        json={"value": {"token": "abc"}},
        headers=admin_headers,
    )
    assert secret.status_code == 400
    assert secret.json()["error_code"] == "SECRET_VALUE_REJECTED"

    pii = client.patch(
        "/admin/settings/contato",
        json={"value": {"email": "pessoa@example.com"}},
        headers=admin_headers,
    )
    assert pii.status_code == 400
    assert pii.json()["error_code"] == "SECRET_VALUE_REJECTED"

    opaque = client.patch(
        "/admin/settings/integracao",
        json={"value": {"endpoint": "sk-live-AbCdEf1234567890"}},
        headers=admin_headers,
    )
    assert opaque.status_code == 400
    assert opaque.json()["error_code"] == "SECRET_VALUE_REJECTED"


def test_user_creation_rejects_admin_flag_without_mutation(
    client: TestClient, session_factory: sessionmaker[Session], admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/users",
        json={
            "email": "comum2@ressonant.dev",
            "cpf": VALID_CPFS[0],
            "telefone": "11988887777",
            "senha": "senha-forte-1",
            "idade": 30,
            "termos_contrato": True,
            "interno_adm": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ADMIN_FLAG_NOT_ALLOWED"
    with session_factory() as db:
        assert db.scalar(select(User).where(User.email == "comum2@ressonant.dev")) is None


def test_last_admin_is_protected_on_revoke_and_delete(
    client: TestClient, session_factory: sessionmaker[Session], admin_headers: dict[str, str]
) -> None:
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@ressonant.dev"))
        assert admin is not None
        admin_id = admin.id

    revoke = client.patch(
        f"/users/{admin_id}/admin", json={"interno_adm": False}, headers=admin_headers
    )
    assert revoke.status_code == 409
    assert revoke.json()["error_code"] == "LAST_ADMIN_PROTECTED"

    delete = client.delete(f"/users/{admin_id}", headers=admin_headers)
    assert delete.status_code == 409
    assert delete.json()["error_code"] == "LAST_ADMIN_PROTECTED"

    with session_factory() as db:
        unchanged = db.get(User, admin_id)
        assert unchanged is not None
        assert unchanged.interno_adm is True
        assert unchanged.status_ativo is True


def test_inactive_admin_does_not_count_as_survivor(
    client: TestClient, session_factory: sessionmaker[Session], admin_headers: dict[str, str]
) -> None:
    make_user(
        session_factory, email="inativo@ressonant.dev", cpf=VALID_CPFS[1], admin=True, ativo=False
    )
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.email == "admin@ressonant.dev"))
        assert admin is not None
        admin_id = admin.id

    response = client.patch(
        f"/users/{admin_id}/admin", json={"interno_adm": False}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "LAST_ADMIN_PROTECTED"


def test_admin_guard_revalidates_after_lock_window(
    session_factory: sessionmaker[Session],
) -> None:
    """Simula a janela de concorrência: outro admin é revogado após o lock."""
    owner = make_user(
        session_factory, email="lock-owner@ressonant.dev", cpf=VALID_CPFS[0], admin=True
    )
    other = make_user(
        session_factory, email="lock-other@ressonant.dev", cpf=VALID_CPFS[1], admin=True
    )

    class RacingRepository(UserRepository):
        def __init__(self, db: Session, factory: sessionmaker[Session], other_id: str) -> None:
            super().__init__(db)
            self._factory = factory
            self._other_id = other_id

        def lock_active_admin_ids(self) -> list[str]:
            # A revogação concorrente só poderia ocorrer antes de travarmos a
            # varredura determinística; no Postgres ela bloquearia. Aqui
            # forçamos a ordem para provar que a contagem usa o estado travado.
            with self._factory() as racing_db:
                racer = racing_db.get(User, self._other_id)
                assert racer is not None
                racer.status_ativo = False
                racing_db.commit()
            return super().lock_active_admin_ids()

    repo = RacingRepository(session_factory(), session_factory, other.id)
    service = UserService(repo)
    with pytest.raises(ConflictException) as caught:
        service.set_admin(owner.id, False)
    assert caught.value.exception_data.error_code == "LAST_ADMIN_PROTECTED"

    with session_factory() as db:
        assert db.get(User, owner.id).interno_adm is True


def test_seed_prod_catalog_is_idempotent_and_does_not_overwrite(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory() as db:
        db.add(
            Plan(
                code="equipe",
                name="Equipe customizada",
                billing_cycle="yearly",
                base_price_cents=123,
                price_per_seat_cents=7,
                included_seats=2,
                limits={"seats": 2},
                is_public=False,
                is_active=False,
                price_cents=123,
                currency="BRL",
                seat_limit=2,
                overage_cents_per_seat=7,
                trial_days=3,
                active=False,
            )
        )
        db.commit()

    monkeypatch.setattr(seed_catalog, "get_session_factory", lambda: session_factory)
    assert seed_catalog.main() == 0
    assert seed_catalog.main() == 0

    with session_factory() as db:
        plans = {plan.code: plan for plan in db.scalars(select(Plan)).all()}
        assert set(plans) == {"trial_default", "inicial", "equipe", "empresa"}
        assert plans["equipe"].price_cents == 123
        assert plans["equipe"].active is False
        assert plans["equipe"].name == "Equipe customizada"
        trial = plans["trial_default"]
        assert trial.base_price_cents == 0
        assert trial.trial_days == 14
        assert trial.is_public is True
        assert trial.is_active is True
        assert trial.currency == "BRL"


def test_legacy_plan_codes_keep_public_registration_working(
    client: TestClient,
) -> None:
    response = client.post("/auth/register", json=register_payload())
    assert response.status_code == 201, response.text
