from fastapi.testclient import TestClient
from tests.conftest import login, register_payload


def _register(client: TestClient, **overrides: object) -> dict:
    response = client.post("/auth/register", json=register_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_requires_authentication(client: TestClient) -> None:
    assert client.get("/users").status_code == 401
    assert client.post("/users", json=register_payload()).status_code == 401
    assert client.get("/users/qualquer").status_code == 401


def test_regular_user_cannot_use_admin_routes(client: TestClient) -> None:
    _register(client)
    headers = login(client, "ana@ressonant.dev")

    assert client.get("/users", headers=headers).status_code == 403
    assert client.post("/users", json=register_payload(), headers=headers).status_code == 403
    assert client.delete("/users/x", headers=headers).status_code == 403


def test_regular_user_reads_and_updates_only_self(client: TestClient) -> None:
    ana = _register(client)
    bia = _register(client, email="bia@ressonant.dev", cpf="11144477735")
    headers = login(client, "ana@ressonant.dev")

    assert client.get(f"/users/{ana['id']}", headers=headers).status_code == 200
    assert client.get(f"/users/{bia['id']}", headers=headers).status_code == 403

    body = {"email": "ana@ressonant.dev", "telefone": "1133334444", "idade": 40}
    updated = client.put(f"/users/{ana['id']}", json=body, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["telefone"] == "1133334444"
    assert client.put(f"/users/{bia['id']}", json=body, headers=headers).status_code == 403


def test_admin_creates_admin_user(client: TestClient, admin_headers) -> None:
    response = client.post("/users", json=register_payload(interno_adm=True), headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["interno_adm"] is True


def test_admin_list_pagination_and_filter(client: TestClient, admin_headers) -> None:
    first = _register(client)
    _register(client, email="bia@ressonant.dev", cpf="11144477735")
    client.patch(
        f"/users/{first['id']}/status", json={"status_ativo": False}, headers=admin_headers
    )

    everyone = client.get("/users", headers=admin_headers).json()
    active = client.get("/users?status_ativo=true", headers=admin_headers).json()
    inactive = client.get("/users?status_ativo=false", headers=admin_headers).json()
    page = client.get("/users?skip=1&limit=1", headers=admin_headers).json()

    assert everyone["total"] == 3
    assert active["total"] == 2
    assert [u["email"] for u in inactive["items"]] == ["ana@ressonant.dev"]
    assert page["total"] == 3 and len(page["items"]) == 1
    assert client.get("/users?limit=1000", headers=admin_headers).status_code == 422


def test_update_rejects_email_taken_by_another_user(client: TestClient, admin_headers) -> None:
    ana = _register(client)
    _register(client, email="bia@ressonant.dev", cpf="11144477735")

    response = client.put(
        f"/users/{ana['id']}",
        json={"email": "bia@ressonant.dev", "telefone": "11987654321", "idade": 30},
        headers=admin_headers,
    )

    assert response.status_code == 409


def test_update_cannot_change_cpf_or_flags(client: TestClient, admin_headers) -> None:
    ana = _register(client)

    response = client.put(
        f"/users/{ana['id']}",
        json={
            "email": "ana@ressonant.dev",
            "telefone": "11987654321",
            "idade": 30,
            "cpf": "11144477735",
            "interno_adm": True,
        },
        headers=admin_headers,
    )

    assert response.json()["cpf"] == "52998224725"
    assert response.json()["interno_adm"] is False


def test_delete_is_soft_and_idempotent(client: TestClient, admin_headers) -> None:
    ana = _register(client)

    assert client.delete(f"/users/{ana['id']}", headers=admin_headers).status_code == 204
    assert client.delete(f"/users/{ana['id']}", headers=admin_headers).status_code == 204
    fetched = client.get(f"/users/{ana['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["status_ativo"] is False


def test_unknown_or_malformed_id_is_404(client: TestClient, admin_headers) -> None:
    assert client.get("/users/nao-e-uuid", headers=admin_headers).status_code == 404
    missing = client.get("/users/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "USER_NOT_FOUND"


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "service": "ressonant_backend"}
    assert client.get("/health/ready").status_code == 200
