"""CYB-006 — o JWT do convidado precisa carregar a sessão nos dois endpoints.

Arquivo dedicado (em vez de editar `test_auth.py`/`test_context.py`) porque a
regressão só aparece quando o *mesmo* token de um aceite real é usado em
`/auth/me` e `/me/context`. As fixtures de convite são reaproveitadas do teste
de segurança BE-03, sem duplicar regra de negócio.
"""

from __future__ import annotations

import json

from tests.conftest import VALID_CPFS, login, register_payload
from tests.test_security_invite_flow import (
    _accept_payload,
    _add_invitation,
    _seed_context,
)


def _assert_sanitized(body: object) -> str:
    """Nenhum campo de resposta de sessão pode trazer o hash da senha."""
    serialized = json.dumps(body)
    assert "senha_hash" not in serialized
    return serialized


def test_invited_jwt_loads_auth_me_and_me_context(client, session_factory) -> None:
    ctx = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        ctx,
        personal_email="sessao.pessoal@example.com",
        corporate_email="sessao.corp@example.com",
        team_id=ctx["team_id"],
    )
    accepted = client.post("/auth/register/invitation", json=_accept_payload(token, VALID_CPFS[0]))
    assert accepted.status_code == 201, accepted.text
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["email"] == "sessao.corp@example.com"
    assert me_body["telefone"] is None
    assert me_body["idade"] is None
    assert me_body["cpf"] == VALID_CPFS[0]
    _assert_sanitized(me_body)

    context = client.get("/me/context", headers=headers)
    assert context.status_code == 200, context.text
    context_body = context.json()
    user = context_body["user"]
    assert user["id"] == me_body["id"]
    assert user["email"] == me_body["email"]
    assert user["telefone"] is None
    assert user["idade"] is None
    assert any(item["id"] == ctx["org_id"] for item in context_body["organizations"])
    assert context_body["active_organization"]["id"] == ctx["org_id"]
    assert any(item["id"] == ctx["ws_id"] for item in context_body["workspaces"])
    assert context_body["permission_version"] >= 1
    _assert_sanitized(context_body)


def test_owner_jwt_still_loads_both_session_endpoints(client, session_factory) -> None:
    ctx = _seed_context(session_factory)
    headers = login(client, ctx["owner_email"])

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["telefone"] == "11999990000"
    assert me.json()["idade"] == 30

    context = client.get("/me/context", headers=headers)
    assert context.status_code == 200, context.text
    user = context.json()["user"]
    assert user["telefone"] == "11999990000"
    assert user["idade"] == 30
    assert user["email"] == ctx["owner_email"]
    _assert_sanitized(context.json())


def test_input_validation_was_not_weakened(client, session_factory) -> None:
    """Opcionalidade é só na resposta: cadastro público continua exigindo os campos."""
    payload = register_payload()
    payload.pop("telefone")
    without_phone = client.post("/auth/register", json=payload)
    assert without_phone.status_code == 422, without_phone.text

    payload = register_payload()
    payload.pop("idade")
    without_age = client.post("/auth/register", json=payload)
    assert without_age.status_code == 422, without_age.text

    ctx = _seed_context(session_factory)
    token = _add_invitation(
        session_factory,
        ctx,
        personal_email="invalido.pessoal@example.com",
        corporate_email="invalido.corp@example.com",
    )
    bad_cpf = client.post("/auth/register/invitation", json=_accept_payload(token, "11111111111"))
    assert bad_cpf.status_code == 422, bad_cpf.text

    no_terms = client.post(
        "/auth/register/invitation",
        json={**_accept_payload(token, VALID_CPFS[1]), "termos_contrato": False},
    )
    assert no_terms.status_code == 422, no_terms.text
