import hashlib
import json
import uuid
from types import SimpleNamespace

from app.modules.kanban_cards.dataproviders.repository import CardRepository
from app.modules.kanban_cards.domain.models import (
    Card,
    CardChecklist,
    CardComment,
    CardCustomField,
    CardHistory,
    CardLink,
    CardSubtask,
    CardWatcher,
    CardWorklog,
)
from app.modules.teams.domain.models import TeamMember
from app.modules.workspace_management.domain.models import AuditEvent
from app.user.models import User
from sqlalchemy import func, select
from tests.conftest import VALID_CPFS, login
from tests.conftest import make_user as plain_make_user
from tests.test_kanban_cards import _create_board

COMMENT_BODY = "Comentário persistido pelo TestClient"
FIELD_VALUE = "valor-sensivel-que-nao-deve-entrar-na-auditoria"


def _create_card(client, board, headers, title="Card de teste", **extra):
    response = client.post(
        "/cards",
        json={
            "title": title,
            "board_id": board["id"],
            "team_id": board["team_id"],
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _delete(client, card_id, headers, **payload):
    return client.request("DELETE", f"/cards/{card_id}", json=payload or None, headers=headers)


def _owner_id(session_factory) -> str:
    with session_factory() as db:
        return db.scalar(select(User.id).where(User.email == "ana@ressonant.dev"))


def _card_key(session_factory, card_id) -> str:
    with session_factory() as db:
        return db.get(Card, card_id).key


def _card_keys(session_factory, board_id) -> list[str]:
    with session_factory() as db:
        stmt = select(Card.key).where(Card.board_id == board_id).order_by(Card.key)
        return list(db.scalars(stmt))


def _audit_events(session_factory, action=None) -> list[AuditEvent]:
    with session_factory() as db:
        stmt = select(AuditEvent)
        if action is not None:
            stmt = stmt.where(AuditEvent.action == action)
        return list(db.scalars(stmt))


def _count(session_factory, model, card_id) -> int:
    with session_factory() as db:
        return int(
            db.scalar(select(func.count()).select_from(model).where(model.card_id == card_id)) or 0
        )


# --- BUG-T3-015: contrato de comentários ---


def test_create_comment_uses_jwt_author_and_survives_get(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers)
    owner_id = _owner_id(session_factory)

    response = client.post(
        f"/cards/{card['id']}/comments",
        json={"body": f"  {COMMENT_BODY}  ", "author_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["card_id"] == card["id"]
    assert created["author_id"] == owner_id  # mass assignment via body ignorado
    assert created["body"] == COMMENT_BODY
    assert created["id"] and created["criado_em"]

    listed = client.get(f"/cards/{card['id']}/comments", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0] == created
    with session_factory() as db:
        stored = db.scalar(select(CardComment.body).where(CardComment.card_id == card["id"]))
    assert stored == COMMENT_BODY  # persistência real, não apenas resposta otimista


def test_comment_routes_auth_and_validation(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers)

    assert client.post(f"/cards/{card['id']}/comments", json={"body": "oi"}).status_code == 401
    assert client.get(f"/cards/{card['id']}/comments").status_code == 401
    assert (
        client.post(f"/cards/{card['id']}/comments", json={"body": ""}, headers=headers).status_code
        == 422
    )
    assert (
        client.post(
            f"/cards/{card['id']}/comments", json={"body": "x" * 2001}, headers=headers
        ).status_code
        == 422
    )
    unknown = str(uuid.uuid4())
    assert (
        client.post(f"/cards/{unknown}/comments", json={"body": "oi"}, headers=headers).status_code
        == 404
    )
    assert _count(session_factory, CardComment, card["id"]) == 0


# --- BUG-T3-016: exclusão, travessia e auditoria ---


def test_delete_card_with_child_returns_409_without_audit(client, session_factory):
    board, headers = _create_board(client, session_factory)
    parent = _create_card(client, board, headers, title="Pai")
    _create_card(client, board, headers, title="Filho", parent_id=parent["id"])

    response = _delete(client, parent["id"], headers, reason="teste")
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_HAS_CHILDREN"
    assert client.get(f"/cards/{parent['id']}", headers=headers).status_code == 200
    assert _audit_events(session_factory, "card.deleted") == []


def test_delete_card_with_inactive_child_also_returns_409(client, session_factory):
    board, headers = _create_board(client, session_factory)
    parent = _create_card(client, board, headers, title="Pai")
    child = _create_card(client, board, headers, title="Filho inativo", parent_id=parent["id"])
    with session_factory() as db:
        db.get(Card, child["id"]).status_ativo = False
        db.commit()

    response = _delete(client, parent["id"], headers)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_HAS_CHILDREN"


def test_delete_card_with_worklogs_returns_409(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers)
    owner_id = _owner_id(session_factory)
    with session_factory() as db:
        db.add(
            CardWorklog(
                card_id=card["id"], author_id=owner_id, time_spent_minutes=120, comment="horas"
            )
        )
        db.commit()

    response = _delete(client, card["id"], headers)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_HAS_WORKLOGS"
    assert client.get(f"/cards/{card['id']}", headers=headers).status_code == 200


def test_delete_card_returns_204_and_writes_one_card_scoped_audit_event(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers, title="Card descartável")
    card_key = _card_key(session_factory, card["id"])
    owner_id = _owner_id(session_factory)
    comment = client.post(
        f"/cards/{card['id']}/comments", json={"body": COMMENT_BODY}, headers=headers
    )
    assert comment.status_code == 201, comment.text

    with session_factory() as db:
        db.get(Card, card["id"]).description = "descrição privada do card"
        db.add_all(
            [
                CardSubtask(card_id=card["id"], key="TIMETESTE-1.1", title="sub"),
                CardChecklist(card_id=card["id"], title="item"),
                CardCustomField(card_id=card["id"], field_key="cpf", field_value=FIELD_VALUE),
                CardLink(card_id=card["id"], url="https://example.test"),
                CardWatcher(card_id=card["id"], user_id=owner_id),
                CardHistory(card_id=card["id"], event_type="created"),
            ]
        )
        db.commit()

    response = _delete(client, card["id"], headers, reason="card criado por engano")
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert client.get(f"/cards/{card['id']}", headers=headers).status_code == 404

    events = _audit_events(session_factory, "card.deleted")
    assert len(events) == 1
    event = events[0]
    assert event.scope == "card"
    assert event.entity_type == "card"
    assert event.entity_id == card["id"]
    assert event.actor_user_id == owner_id
    assert event.actor_type == "user"
    assert event.result == "success"
    assert event.workspace_id == board["workspace_id"]
    assert event.organization_id is None
    assert event.metadata_["reason"] == "card criado por engano"
    assert event.before["key"] == card_key
    assert event.before["dependencies"]["comments"] == 1
    assert event.before["custom_field_keys"] == ["cpf"]
    assert "field_value" not in json.dumps(event.before, ensure_ascii=False)
    assert "descrição privada" not in json.dumps(event, default=str, ensure_ascii=False)
    assert COMMENT_BODY not in json.dumps(event, default=str, ensure_ascii=False)
    assert FIELD_VALUE not in json.dumps(event, default=str, ensure_ascii=False)

    for model in (
        CardComment,
        CardSubtask,
        CardChecklist,
        CardCustomField,
        CardLink,
        CardWatcher,
        CardHistory,
    ):
        assert _count(session_factory, model, card["id"]) == 0


def test_delete_card_403_for_viewer(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers)
    viewer = plain_make_user(session_factory, email="viewer@ressonant.dev", cpf=VALID_CPFS[1])
    viewer_headers = login(client, "viewer@ressonant.dev")
    with session_factory() as db:
        db.add(TeamMember(team_id=board["team_id"], user_id=viewer.id, role="viewer"))
        db.commit()

    response = _delete(client, card["id"], viewer_headers)
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "FORBIDDEN"
    comment = client.post(
        f"/cards/{card['id']}/comments", json={"body": "viewer"}, headers=viewer_headers
    )
    assert comment.status_code == 403, comment.text
    assert client.get(f"/cards/{card['id']}", headers=headers).status_code == 200


def test_delete_card_version_conflict_keeps_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    card = _create_card(client, board, headers)

    response = _delete(client, card["id"], headers, expected_version=card["version"] + 1)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_VERSION_CONFLICT"
    assert client.get(f"/cards/{card['id']}", headers=headers).status_code == 200
    assert _audit_events(session_factory, "card.deleted") == []


def test_next_key_uses_max_plus_one_after_deleting_middle_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    cards = [_create_card(client, board, headers, title=f"Card {i}") for i in range(1, 4)]
    assert _card_keys(session_factory, board["id"]) == [
        "TIMETESTE-1",
        "TIMETESTE-2",
        "TIMETESTE-3",
    ]

    deleted = _delete(client, cards[1]["id"], headers)
    assert deleted.status_code == 204, deleted.text
    new_card = _create_card(client, board, headers, title="Card 4")
    assert new_card["id"]
    assert _card_keys(session_factory, board["id"]) == [
        "TIMETESTE-1",
        "TIMETESTE-3",
        "TIMETESTE-4",
    ]


def test_create_card_with_parent_acquires_same_advisory_lock(client, session_factory, monkeypatch):
    board, headers = _create_board(client, session_factory)
    parent = _create_card(client, board, headers)
    calls = []
    original = CardRepository.lock_card

    def spy(self, card_id):
        calls.append(card_id)
        return original(self, card_id)

    monkeypatch.setattr(CardRepository, "lock_card", spy)
    child = _create_card(client, board, headers, title="Filho", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]
    assert calls == [parent["id"]]


def test_postgres_advisory_lock_key_is_deterministic_and_uuid_normalized():
    calls = []

    class FakeBind:
        dialect = SimpleNamespace(name="postgresql")

    class FakeDb:
        def get_bind(self):
            return FakeBind()

        def execute(self, statement, params):
            calls.append((str(statement), params))

    repository = CardRepository(FakeDb())  # type: ignore[arg-type]
    card_id = "31a4ab2d-1111-2222-3333-444455556666"
    repository.lock_card(card_id)
    repository.lock_card(card_id.upper())

    expected = int.from_bytes(
        hashlib.sha256(str(uuid.UUID(card_id)).encode("ascii")).digest()[:8],
        "big",
        signed=True,
    )
    assert len(calls) == 2
    assert "pg_advisory_xact_lock" in calls[0][0]
    assert calls[0][1] == {"key": expected}
    assert calls[1][1] == calls[0][1]
