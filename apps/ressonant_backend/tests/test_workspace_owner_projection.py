import uuid

from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.user.domain.models import User
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, login, make_user


def _make_org_user(session_factory: sessionmaker[Session], *, email: str, cpf: str):
    user = make_user(session_factory, email=email, cpf=cpf)
    with session_factory() as db:
        organization = Organization(name=f"Org {user.id}", slug=f"org-{uuid.uuid4().hex[:8]}")
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


def test_transfer_owner_keeps_role_projection_in_sync(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    owner = _make_org_user(session_factory, email="owner@ressonant.dev", cpf=VALID_CPFS[0])
    new_owner = _make_org_user(session_factory, email="novo-owner@ressonant.dev", cpf=VALID_CPFS[1])
    headers = login(client, owner.email)

    created = client.post(
        "/workspaces",
        json={"name": "Plataforma", "slug": "plataforma"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    workspace_id = created.json()["id"]

    added = client.post(
        f"/workspaces/{workspace_id}/members",
        json={"user_id": new_owner.id, "role": "member"},
        headers=headers,
    )
    assert added.status_code == 201, added.text

    transferred = client.patch(
        f"/workspaces/{workspace_id}/members/{new_owner.id}",
        json={"role": "owner"},
        headers=headers,
    )
    assert transferred.status_code == 200, transferred.text

    with session_factory() as db:
        workspace = db.get(Workspace, workspace_id)
        assert workspace is not None
        assert workspace.owner_id == new_owner.id
        old_member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == owner.id,
            )
        )
        assert old_member is not None
        assert old_member.role == "admin"
        new_member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == new_owner.id,
            )
        )
        assert new_member is not None
        assert new_member.role == "owner"

    context = client.get("/me/context", headers=login(client, new_owner.email))
    assert context.status_code == 200, context.text
    workspaces = [item for item in context.json()["workspaces"] if item["id"] == workspace_id]
    assert len(workspaces) == 1
    assert workspaces[0]["role"] == "owner"

    with session_factory() as db:
        promoted = db.get(User, new_owner.id)
        assert promoted is not None
        assert promoted.interno_adm is False
