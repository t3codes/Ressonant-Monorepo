from datetime import UTC, datetime, timedelta

import jwt
from app.config.settings import get_settings
from fastapi.testclient import TestClient
from tests.conftest import VALID_CPFS, login, make_user, register_payload


def test_register_creates_regular_active_user(client: TestClient) -> None:
    response = client.post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["cpf"] == "52998224725"
    assert body["telefone"] == "11987654321"
    assert body["interno_adm"] is False
    assert body["status_ativo"] is True
    assert "senha" not in body and "senha_hash" not in body


def test_register_ignores_admin_flags(client: TestClient) -> None:
    response = client.post(
        "/auth/register", json=register_payload(interno_adm=True, status_ativo=False)
    )

    assert response.status_code == 201
    assert response.json()["interno_adm"] is False
    assert response.json()["status_ativo"] is True


def test_register_rejects_duplicate_email_or_cpf(client: TestClient) -> None:
    client.post("/auth/register", json=register_payload())

    same_email = client.post("/auth/register", json=register_payload(cpf="11144477735"))
    same_cpf = client.post("/auth/register", json=register_payload(email="outra@ressonant.dev"))

    assert same_email.status_code == 409
    assert same_cpf.status_code == 409


def test_register_validation(client: TestClient) -> None:
    for override in (
        {"cpf": "111.111.111-11"},
        {"cpf": "123.456.789-00"},
        {"senha": "curta"},
        {"idade": 17},
        {"termos_contrato": False},
        {"telefone": "123"},
        {"email": "nao-e-email"},
    ):
        response = client.post("/auth/register", json=register_payload(**override))
        assert response.status_code == 422, override


def test_password_is_not_stored_as_plain_hash(client: TestClient, session_factory) -> None:
    client.post("/auth/register", json=register_payload())

    with session_factory() as db:
        from app.user.models import User

        stored = db.query(User).one().senha_hash
    assert stored.startswith("$argon2id$")


def test_login_returns_token_and_me_works(client: TestClient) -> None:
    client.post("/auth/register", json=register_payload())

    headers = login(client, "ANA@ressonant.dev")
    me = client.get("/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["email"] == "ana@ressonant.dev"


def test_login_failures_are_indistinguishable(client: TestClient, session_factory) -> None:
    client.post("/auth/register", json=register_payload())
    make_user(session_factory, email="off@ressonant.dev", cpf=VALID_CPFS[1], ativo=False)

    wrong_password = client.post(
        "/auth/login", json={"email": "ana@ressonant.dev", "senha": "errada-123"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "ninguem@ressonant.dev", "senha": "senha-forte-1"}
    )
    inactive = client.post(
        "/auth/login", json={"email": "off@ressonant.dev", "senha": "senha-forte-1"}
    )

    assert wrong_password.status_code == unknown_email.status_code == inactive.status_code == 401
    assert wrong_password.json() == unknown_email.json() == inactive.json()


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_expired_and_wrong_type_tokens_are_rejected(client: TestClient, session_factory) -> None:
    user = make_user(session_factory, email="a@ressonant.dev", cpf=VALID_CPFS[0])
    settings = get_settings()
    now = datetime.now(UTC)

    def token(**claims: object) -> dict[str, str]:
        payload = {"sub": user.id, "type": "access", "exp": now + timedelta(minutes=5), **claims}
        encoded = jwt.encode(payload, settings.auth_secret, algorithm="HS256")
        return {"Authorization": f"Bearer {encoded}"}

    assert client.get("/auth/me", headers=token()).status_code == 200
    assert client.get("/auth/me", headers=token(exp=now - timedelta(minutes=1))).status_code == 401
    assert client.get("/auth/me", headers=token(type="refresh")).status_code == 401


def test_deactivated_user_loses_access_with_existing_token(
    client: TestClient, session_factory, admin_headers
) -> None:
    created = client.post("/auth/register", json=register_payload()).json()
    headers = login(client, "ana@ressonant.dev")

    client.patch(
        f"/users/{created['id']}/status", json={"status_ativo": False}, headers=admin_headers
    )

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_logout_revokes_access_token(client: TestClient) -> None:
    client.post("/auth/register", json=register_payload())
    headers = login(client, "ana@ressonant.dev")

    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_login_rate_limit_blocks_after_five_failed_attempts(client: TestClient) -> None:
    client.post("/auth/register", json=register_payload())

    responses = [
        client.post(
            "/auth/login",
            json={"email": "ana@ressonant.dev", "senha": "senha-incorreta"},
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401, 401, 429]
