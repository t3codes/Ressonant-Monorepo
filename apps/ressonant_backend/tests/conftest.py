import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_SECRET"] = "test-secret-with-at-least-32-characters!!"

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from app.common.security import hash_password  # noqa: E402
from app.database.engine import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.user.models import User  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

VALID_CPFS = ["52998224725", "11144477735", "39053344705", "16899535009"]


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_db() -> Iterator[Session]:
        with session_factory() as session:
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
        "email": "ana@ressonant.dev",
        "senha": "senha-forte-1",
        "cpf": "529.982.247-25",
        "idade": 25,
        "termos_contrato": True,
        "telefone": "(11) 98765-4321",
    }
    payload.update(overrides)
    return payload
