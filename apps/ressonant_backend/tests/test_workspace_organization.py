"""Regressão do F0-H1: organization_id é gravado pela criação de workspace."""

from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.conftest import VALID_CPFS, login, make_user


def _seed_org(
    session_factory,
    user_id: str,
    slug: str,
    *,
    role: str = "owner",
    status: str = "active",
) -> str:
    """Cria organização com membership explícita, sem depender do hook do conftest."""
    with session_factory() as db:
        organization = Organization(name=f"Org {slug}", slug=f"org-{slug}")
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user_id,
                role=role,
                status=status,
            )
        )
        db.commit()
        return organization.id


def _row_counts(session_factory) -> tuple[int, int]:
    with session_factory() as db:
        return (
            db.scalar(select(func.count()).select_from(Workspace)) or 0,
            db.scalar(select(func.count()).select_from(WorkspaceMember)) or 0,
        )


def test_create_without_organization_id_uses_single_eligible_org(
    client: TestClient, session_factory
) -> None:
    user = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    org_id = _seed_org(session_factory, user.id, "unica")
    headers = login(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    )
    assert response.status_code == 201, response.text

    workspace_id = response.json()["id"]
    with session_factory() as db:
        workspace = db.get(Workspace, workspace_id)
        assert workspace is not None
        assert workspace.organization_id == org_id
        member = db.scalar(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )
        assert member is not None
        assert member.user_id == user.id
        assert member.role == "admin"


def test_create_with_explicit_organization_id(client: TestClient, session_factory) -> None:
    user = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    chosen_org = _seed_org(session_factory, user.id, "escolhida")
    _seed_org(session_factory, user.id, "outra")
    headers = login(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces",
        json={
            "name": "Plataforma",
            "slug": "plataforma",
            "organization_id": chosen_org,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    with session_factory() as db:
        workspace = db.get(Workspace, response.json()["id"])
        assert workspace is not None
        assert workspace.organization_id == chosen_org


def test_create_with_other_users_organization_is_forbidden(
    client: TestClient, session_factory
) -> None:
    owner = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    _seed_org(session_factory, owner.id, "ana")
    other = make_user(session_factory, email="bia@ressonant.dev", cpf=VALID_CPFS[1])
    foreign_org = _seed_org(session_factory, other.id, "bia")
    headers = login(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces",
        json={
            "name": "Plataforma",
            "slug": "plataforma",
            "organization_id": foreign_org,
        },
        headers=headers,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error_code"] == "ORGANIZATION_FORBIDDEN"
    assert _row_counts(session_factory) == (0, 0)


def test_create_without_any_organization_fails_without_orphan(
    client: TestClient, session_factory
) -> None:
    make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    headers = login(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    )
    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "ORGANIZATION_NOT_FOUND"
    assert _row_counts(session_factory) == (0, 0)


def test_create_with_two_eligible_organizations_requires_explicit_id(
    client: TestClient, session_factory
) -> None:
    user = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    first_org = _seed_org(session_factory, user.id, "primeira")
    _seed_org(session_factory, user.id, "segunda")
    headers = login(client, "ana@ressonant.dev")

    ambiguous = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    )
    assert ambiguous.status_code == 409, ambiguous.text
    assert ambiguous.json()["error_code"] == "ORGANIZATION_AMBIGUOUS"
    assert _row_counts(session_factory) == (0, 0)

    resolved = client.post(
        "/workspaces",
        json={
            "name": "Plataforma",
            "slug": "plataforma",
            "organization_id": first_org,
        },
        headers=headers,
    )
    assert resolved.status_code == 201, resolved.text
    assert _row_counts(session_factory) == (1, 1)


def test_inactive_or_member_role_is_not_eligible(client: TestClient, session_factory) -> None:
    user = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    _seed_org(session_factory, user.id, "membro", role="member")
    _seed_org(session_factory, user.id, "inativa", status="inactive")
    headers = login(client, "ana@ressonant.dev")

    response = client.post(
        "/workspaces", json={"name": "Plataforma", "slug": "plataforma"}, headers=headers
    )
    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "ORGANIZATION_NOT_FOUND"
    assert _row_counts(session_factory) == (0, 0)
