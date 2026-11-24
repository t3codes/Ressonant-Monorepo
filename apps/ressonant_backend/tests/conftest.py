import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_SECRET"] = "test-secret-with-at-least-32-characters!!"

import re  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from app.common.security import hash_password  # noqa: E402
from app.database.engine import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.usecases.services import _rate_limit  # noqa: E402
from app.modules.billing.domain.models import Plan  # noqa: E402
from app.modules.kanban_cards.domain.models import Card  # noqa: E402
from app.modules.organization.domain.email_outbox import EmailOutbox  # noqa: E402
from app.modules.organization.domain.models import (  # noqa: E402
    Invitation,
    Organization,
    OrganizationMember,
)
from app.modules.teams.domain.models import Team  # noqa: E402
from app.modules.workspace.domain.models import Workspace  # noqa: E402
from app.user.models import User  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

VALID_CPFS = ["52998224725", "11144477735", "39053344705", "16899535009"]


@event.listens_for(Session, "before_flush")
def _fill_0015_required_columns(
    session: Session, _flush_context: object, _instances: object
) -> None:
    """Test scaffolding: rotas pré-0015 não recebem organization_id/key_prefix/key."""
    new_objects = list(session.new)

    for obj in new_objects:
        if isinstance(obj, Workspace) and obj.organization_id is None:
            organization = Organization(
                id=str(uuid.uuid4()),
                name=obj.name,
                slug=obj.slug[:100],
            )
            session.add(organization)
            obj.organization_id = organization.id
            session.add(
                OrganizationMember(
                    organization_id=organization.id,
                    user_id=obj.owner_id,
                    role="owner",
                    status="active",
                )
            )

    for obj in new_objects:
        if isinstance(obj, Team) and obj.key_prefix is None:
            obj.key_prefix = re.sub(r"[^A-Za-z0-9]", "", obj.slug).upper()[:20] or "TEAM"

    prefixes = {row[0]: row[1] for row in session.execute(select(Team.id, Team.key_prefix))}
    prefixes.update({obj.id: obj.key_prefix for obj in new_objects if isinstance(obj, Team)})
    sequences: dict[str, int] = {}
    for obj in new_objects:
        if isinstance(obj, Card) and obj.key is None:
            count = sequences.get(obj.team_id)
            if count is None:
                count = len(
                    session.execute(select(Card.id).where(Card.team_id == obj.team_id)).all()
                )
            count += 1
            sequences[obj.team_id] = count
            obj.key = f"{prefixes.get(obj.team_id, 'TEAM')}-{count}"[:50]


@pytest.fixture(autouse=True)
def reset_rate_limit_state() -> Iterator[None]:
    with _rate_limit._lock:
        _rate_limit.attempts.clear()
    yield


def seed_billing_plans(session: Session) -> None:
    existing = {code for (code,) in session.execute(select(Plan.code)).all()}
    defaults = [
        Plan(
            code="inicial",
            name="Inicial",
            price_cents=0,
            currency="BRL",
            seat_limit=3,
            trial_days=7,
            active=True,
        ),
        Plan(
            code="equipe",
            name="Equipe",
            price_cents=4900,
            currency="BRL",
            seat_limit=15,
            trial_days=14,
            active=True,
        ),
        Plan(
            code="empresa",
            name="Empresa",
            price_cents=7900,
            currency="BRL",
            seat_limit=None,
            trial_days=14,
            active=True,
        ),
    ]
    pending = [plan for plan in defaults if plan.code not in existing]
    if pending:
        session.add_all(pending)
        session.commit()


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    plans_seeded = False

    def override_db() -> Iterator[Session]:
        nonlocal plans_seeded
        with session_factory() as session:
            if not plans_seeded:
                seed_billing_plans(session)
                plans_seeded = True
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    cpf: str,
    senha: str = "senha-forte-1",
    admin: bool = False,
    ativo: bool = True,
) -> User:
    with session_factory() as db:
        user = User(
            email=email,
            senha_hash=hash_password(senha),
            cpf=cpf,
            idade=30,
            termos_contrato=True,
            telefone="11987654321",
            status_ativo=ativo,
            interno_adm=admin,
        )
        db.add(user)
        db.commit()
        return user


def login(client: TestClient, email: str, senha: str = "senha-forte-1") -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "senha": senha})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient, session_factory: sessionmaker[Session]) -> dict[str, str]:
    make_user(session_factory, email="admin@ressonant.dev", cpf=VALID_CPFS[3], admin=True)
    return login(client, "admin@ressonant.dev")


def register_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "nome_completo": "Ana Silva",
        "cargo": "Dono da Empresa",
        "email": "ana@ressonant.dev",
        "senha": "senha-forte-1",
        "cpf": "529.982.247-25",
        "idade": 25,
        "termos_contrato": True,
        "telefone": "(11) 98765-4321",
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
    payload.update(overrides)
    return payload
