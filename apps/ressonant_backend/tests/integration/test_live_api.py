"""Integração real: API + PostgreSQL no ar (sem mocks, sem override de banco).

Uso: API_BASE_URL=http://localhost:8000 pytest tests/integration
Sem API_BASE_URL os testes são pulados (a suíte unitária roda em SQLite).
"""

import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="defina API_BASE_URL para rodar")

PASSWORD = "senha-forte-1"


@pytest.fixture
def api() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        yield client


def _unique_cpf() -> str:
    """CPF válido e único por execução (os dígitos verificadores são calculados)."""
    base = [int(c) for c in f"{uuid.uuid4().int % 10**9:09d}"]
    if len(set(base)) == 1:
        base[0] = (base[0] + 1) % 10
    digits = base[:]
    for size in (9, 10):
        total = sum(d * w for d, w in zip(digits[:size], range(size + 1, 1, -1), strict=True))
        digits.append((total * 10 % 11) % 10)
    return "".join(map(str, digits))


def _payload(email: str, cpf: str) -> dict:
    return {
        "nome_completo": "Ana Silva",
        "cargo": "Dono da Empresa",
        "email": email,
        "senha": PASSWORD,
        "cpf": cpf,
        "telefone": "11987654321",
        "idade": 30,
        "termos_contrato": True,
        "organizacao": {
            "nome": "Acme Ltda",
            "slug": f"acme-{uuid.uuid4().hex[:8]}",
            "corporate_domain": "example.com",
        },
        "plano_id": "equipe",
        "workspace_nome": "Acme Ltda",
        "equipe_inicial_nome": "Engenharia",
        "convidados": [],
    }


def test_health_and_readiness(api: httpx.Client) -> None:
    assert api.get("/health").json()["status"] == "ok"
    assert api.get("/health/ready").status_code == 200  # consulta o banco


def test_register_login_me_roundtrip_persists(api: httpx.Client) -> None:
    email = f"it-{uuid.uuid4().hex[:12]}@example.com"
    cpf = _unique_cpf()

    created = api.post("/auth/register", json=_payload(email, cpf))
    assert created.status_code == 201
    body = created.json()
    user = body["user"]
    assert user["email"] == email
    assert user["interno_adm"] is False
    assert "senha" not in user and "senha_hash" not in user

    duplicate = api.post("/auth/register", json=_payload(email, cpf))
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "USER_ALREADY_EXISTS"

    login = api.post("/auth/login", json={"email": email, "senha": PASSWORD})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]  # persistido e lido de volta do Postgres


def test_login_rejects_wrong_password_and_unknown_email_identically(api: httpx.Client) -> None:
    wrong = api.post("/auth/login", json={"email": "nao-existe@example.com", "senha": "x" * 8})
    assert wrong.status_code == 401
    assert wrong.json()["error_code"] == "INVALID_CREDENTIALS"


def test_protected_routes_require_valid_token(api: httpx.Client) -> None:
    assert api.get("/auth/me").status_code == 401
    assert api.get("/users", headers={"Authorization": "Bearer invalido"}).status_code == 401


def test_register_validates_payload(api: httpx.Client) -> None:
    invalid_cpf = _payload(f"it-{uuid.uuid4().hex[:12]}@example.com", "11111111111")
    assert api.post("/auth/register", json=invalid_cpf).status_code == 422
    assert api.post("/auth/register", json={"email": "x"}).status_code == 422
