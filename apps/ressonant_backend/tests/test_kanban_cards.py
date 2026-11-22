from app.modules.kanban_cards.dataproviders.repository import CardRepository
from app.modules.kanban_cards.domain.models import Card
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from tests.conftest import login
from tests.conftest import make_user as _plain_make_user


def make_user(session_factory, **kwargs):
    """Usuário de teste com organização elegível (regra real de criação de workspace)."""
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


def _create_board(client, session_factory, email="ana@ressonant.dev", cpf="52998224725"):
    make_user(session_factory, email=email, cpf=cpf)
    headers = login(client, email)
    ws = client.post(
        "/workspaces", json={"name": "Workspace Teste", "slug": "workspace-teste"}, headers=headers
    ).json()
    team = client.post(
        "/teams",
        json={"name": "Time Teste", "slug": "time-teste", "workspace_id": ws["id"]},
        headers=headers,
    ).json()
    board = client.post(
        "/boards",
        json={
            "name": "Board Teste",
            "slug": "board-teste",
            "workspace_id": ws["id"],
            "team_id": team["id"],
        },
        headers=headers,
    ).json()
    return board, headers


def _create_second_team_board(client, headers, workspace_id):
    team_response = client.post(
        "/teams",
        json={"name": "Outro Time", "slug": "outro-time", "workspace_id": workspace_id},
        headers=headers,
    )
    assert team_response.status_code == 201, team_response.text
    team = team_response.json()
    board_response = client.post(
        "/boards",
        json={
            "name": "Outro Board",
            "slug": "board-outro-time",
            "workspace_id": workspace_id,
            "team_id": team["id"],
        },
        headers=headers,
    )
    assert board_response.status_code == 201, board_response.text
    return team, board_response.json()


def test_create_card_requires_auth(client):
    assert (
        client.post(
            "/cards", json={"title": "Card Teste", "board_id": "x", "team_id": "y"}
        ).status_code
        == 401
    )


def test_create_card_success(client, session_factory):
    board, headers = _create_board(client, session_factory)
    r = client.post(
        "/cards",
        json={"title": "Card Teste", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Card Teste"
    assert body["board_id"] == board["id"]
    assert body["column_id"] is None  # Nasce no backlog


def test_list_cards(client, session_factory):
    board, headers = _create_board(client, session_factory)
    client.post(
        "/cards",
        json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    )
    r = client.get(f"/cards?board_id={board['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1


def test_get_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post(
        "/cards",
        json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    ).json()
    r = client.get(f"/cards/{c['id']}", headers=headers)
    assert r.status_code == 200, r.text


def test_update_card_with_version(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post(
        "/cards",
        json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    ).json()
    r = client.put(
        f"/cards/{c['id']}",
        json={"title": "Card 1 Atualizado", "expected_version": c["version"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Card 1 Atualizado"


def test_move_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post(
        "/cards",
        json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    ).json()
    # Criar uma coluna para mover
    col = client.post(
        f"/boards/{board['id']}/columns",
        json={"name": "Fazendo", "slug": "fazendo", "position": 1},
        headers=headers,
    ).json()
    r = client.post(
        f"/cards/{c['id']}/move",
        json={"column_id": col["id"], "expected_version": c["version"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["column_id"] == col["id"]


def test_clone_card(client, session_factory):
    board, headers = _create_board(client, session_factory)
    c = client.post(
        "/cards",
        json={"title": "Card 1", "board_id": board["id"], "team_id": board["team_id"]},
        headers=headers,
    ).json()
    r = client.post(f"/cards/{c['id']}/clone", headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Cópia de Card 1"
    assert r.json()["id"] != c["id"]


def test_create_card_generates_sequential_keys_from_board_team(client, session_factory):
    board, headers = _create_board(client, session_factory)
    for title in ("Card 1", "Card 2"):
        response = client.post(
            "/cards",
            json={"title": title, "board_id": board["id"], "team_id": board["team_id"]},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    with session_factory() as db:
        keys = db.scalars(
            select(Card.key).where(Card.board_id == board["id"]).order_by(Card.key)
        ).all()

    assert keys == ["TIMETESTE-1", "TIMETESTE-2"]


def test_create_card_uses_board_team_prefix_not_another_team(client, session_factory):
    board, headers = _create_board(client, session_factory)
    _, other_board = _create_second_team_board(client, headers, board["workspace_id"])

    first = client.post(
        "/cards",
        json={
            "title": "Card Outro Time",
            "board_id": other_board["id"],
            "team_id": other_board["team_id"],
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/cards",
        json={
            "title": "Card Time do Board",
            "board_id": board["id"],
            "team_id": board["team_id"],
        },
        headers=headers,
    )
    assert second.status_code == 201, second.text

    with session_factory() as db:
        other_keys = db.scalars(select(Card.key).where(Card.board_id == other_board["id"])).all()
        board_keys = db.scalars(select(Card.key).where(Card.board_id == board["id"])).all()

    assert other_keys == ["OUTROTIME-1"]
    assert board_keys == ["TIMETESTE-1"]


def test_create_card_rejects_team_id_from_another_team(client, session_factory):
    board, headers = _create_board(client, session_factory)
    other_team, _ = _create_second_team_board(client, headers, board["workspace_id"])

    response = client.post(
        "/cards",
        json={
            "title": "Card Invasor",
            "board_id": board["id"],
            "team_id": other_team["id"],
        },
        headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_TEAM_MISMATCH"

    with session_factory() as db:
        total = db.scalar(
            select(func.count()).select_from(Card).where(Card.title == "Card Invasor")
        )
    assert total == 0


def test_create_card_sets_key_before_repository_add(client, session_factory, monkeypatch):
    board, headers = _create_board(client, session_factory)
    observed_keys: list[str | None] = []
    original_add = CardRepository.add

    def spy_add(self, card):
        observed_keys.append(card.key)
        return original_add(self, card)

    monkeypatch.setattr(CardRepository, "add", spy_add)
    response = client.post(
        "/cards",
        json={
            "title": "Card Chave Antecipada",
            "board_id": board["id"],
            "team_id": board["team_id"],
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    assert observed_keys == ["TIMETESTE-1"]


def test_create_card_key_conflict_rolls_back(client, session_factory, monkeypatch):
    board, headers = _create_board(client, session_factory)
    rollbacks: list[bool] = []
    original_rollback = CardRepository.rollback

    def failing_commit(self):
        raise IntegrityError(
            "INSERT INTO cards (key) VALUES (:key)",
            {},
            Exception('duplicate key value violates unique constraint "uq_cards_team_key"'),
        )

    def spy_rollback(self):
        rollbacks.append(True)
        return original_rollback(self)

    monkeypatch.setattr(CardRepository, "commit", failing_commit)
    monkeypatch.setattr(CardRepository, "rollback", spy_rollback)
    response = client.post(
        "/cards",
        json={
            "title": "Card Conflito",
            "board_id": board["id"],
            "team_id": board["team_id"],
        },
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "CARD_KEY_CONFLICT"
    assert rollbacks == [True]
    with session_factory() as db:
        total = db.scalar(
            select(func.count()).select_from(Card).where(Card.title == "Card Conflito")
        )
    assert total == 0


def test_create_card_team_not_found(client, session_factory, monkeypatch):
    board, headers = _create_board(client, session_factory)
    monkeypatch.setattr(TeamRepository, "get_by_id", lambda self, team_id: None)

    response = client.post(
        "/cards",
        json={
            "title": "Card Sem Time",
            "board_id": board["id"],
            "team_id": board["team_id"],
        },
        headers=headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "TEAM_NOT_FOUND"


def test_create_card_team_without_key_prefix(client, session_factory):
    board, headers = _create_board(client, session_factory)
    with session_factory() as db:
        team = db.get(Team, board["team_id"])
        team.key_prefix = ""
        db.commit()

    response = client.post(
        "/cards",
        json={
            "title": "Card Sem Prefixo",
            "board_id": board["id"],
            "team_id": board["team_id"],
        },
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "TEAM_KEY_PREFIX_MISSING"
