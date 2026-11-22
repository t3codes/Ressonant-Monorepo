"""Núcleo dos helpers add-only: gravam na Session, quem chama comita."""

import pytest
from app.common.exceptions import ConflictException
from app.modules.organization.domain.models import Organization, OrganizationMember
from app.modules.teams.dataproviders.repository import TeamRepository
from app.modules.teams.domain.models import Team, TeamMember
from app.modules.teams.schemas.dto import TeamCreate
from app.modules.teams.usecases.services import TeamService
from app.modules.user.dataproviders.repository import UserRepository
from app.modules.user.domain.models import User
from app.modules.user.schemas.dto import UserCreate, UserRegister
from app.modules.user.usecases.services import UserService
from app.modules.workspace.dataproviders.repository import WorkspaceRepository
from app.modules.workspace.domain.models import Workspace, WorkspaceMember
from app.modules.workspace.schemas.dto import WorkspaceCreate
from app.modules.workspace.usecases.services import WorkspaceService
from common.errors import ForbiddenException, NotFoundException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, make_user


def _count_in(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as db:
        return _count_in(db, model)


def _user_payload(cpf: str, *, email: str = "ana@ressonant.dev") -> UserRegister:
    return UserRegister(
        email=email,
        senha="senha-forte-1",
        cpf=cpf,
        idade=30,
        termos_contrato=True,
        telefone="11987654321",
    )


def _seed_org(
    session_factory: sessionmaker[Session],
    user_id: str,
    slug: str,
    *,
    role: str = "owner",
    status: str = "active",
) -> str:
    with session_factory() as db:
        organization = Organization(name=f"Org {slug}", slug=slug)
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


def _seed_owner(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    cpf: str,
    slug: str = "org-ana",
) -> str:
    user = make_user(session_factory, email=email, cpf=cpf)
    _seed_org(session_factory, user.id, slug)
    return user.id


def _seed_workspace(
    session_factory: sessionmaker[Session], owner_id: str, *, slug: str = "plataforma"
) -> str:
    with session_factory() as db:
        workspace = WorkspaceService(WorkspaceRepository(db)).create(
            WorkspaceCreate(name="Plataforma", slug=slug), owner_id
        )
        return workspace.id


def test_add_user_stages_without_commit(session_factory: sessionmaker[Session]) -> None:
    payload = _user_payload(VALID_CPFS[0])

    with session_factory() as db:
        user = UserService(UserRepository(db)).add_user(payload)
        assert user.id
        assert user.senha_hash.startswith("$argon2id$")
        assert db.in_transaction()
        assert _count_in(db, User) == 1

    assert _count(session_factory, User) == 0

    with session_factory() as db:
        UserService(UserRepository(db)).add_user(payload)
        db.commit()

    assert _count(session_factory, User) == 1


def test_public_user_methods_commit(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        service = UserService(UserRepository(db))
        registered = service.register(_user_payload(VALID_CPFS[0]))
        created = service.create(
            UserCreate(
                email="bia@ressonant.dev",
                senha="senha-forte-1",
                cpf=VALID_CPFS[1],
                idade=28,
                termos_contrato=True,
                telefone="11987654321",
                status_ativo=False,
                interno_adm=True,
            )
        )
        assert registered.status_ativo is True
        assert registered.interno_adm is False
        assert created.status_ativo is False
        assert created.interno_adm is True

    assert _count(session_factory, User) == 2


def test_add_user_duplicate_identity_keeps_error_code(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        UserService(UserRepository(db)).add_user(_user_payload(VALID_CPFS[0]))
        db.commit()

    with session_factory() as db:
        service = UserService(UserRepository(db))
        with pytest.raises(ConflictException) as same_email:
            service.add_user(_user_payload(VALID_CPFS[1]))
        assert same_email.value.exception_data.error_code == "USER_ALREADY_EXISTS"
        assert str(same_email.value) == "E-mail ou CPF já cadastrado"

        with pytest.raises(ConflictException) as same_cpf:
            service.add_user(_user_payload(VALID_CPFS[0], email="bia@ressonant.dev"))
        assert same_cpf.value.exception_data.error_code == "USER_ALREADY_EXISTS"

    assert _count(session_factory, User) == 1


def test_add_workspace_stages_without_commit(session_factory: sessionmaker[Session]) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])

    with session_factory() as db:
        workspace = WorkspaceService(WorkspaceRepository(db)).add_workspace(
            WorkspaceCreate(name="Plataforma", slug="plataforma"), owner_id
        )
        assert workspace.organization_id is not None
        assert db.in_transaction()
        assert _count_in(db, Workspace) == 1
        assert _count_in(db, WorkspaceMember) == 1
        member = db.scalar(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)
        )
        assert member is not None
        assert member.user_id == owner_id
        assert member.role == "admin"

    assert _count(session_factory, Workspace) == 0
    assert _count(session_factory, WorkspaceMember) == 0

    with session_factory() as db:
        WorkspaceService(WorkspaceRepository(db)).add_workspace(
            WorkspaceCreate(name="Plataforma", slug="plataforma-confirmada"), owner_id
        )
        db.commit()

    assert _count(session_factory, Workspace) == 1
    assert _count(session_factory, WorkspaceMember) == 1


def test_workspace_create_commits(session_factory: sessionmaker[Session]) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])

    with session_factory() as db:
        workspace = WorkspaceService(WorkspaceRepository(db)).create(
            WorkspaceCreate(name="Plataforma", slug="plataforma"), owner_id
        )
        assert workspace.id

    assert _count(session_factory, Workspace) == 1
    assert _count(session_factory, WorkspaceMember) == 1


def test_add_workspace_duplicate_slug_keeps_error_code(
    session_factory: sessionmaker[Session],
) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    _seed_workspace(session_factory, owner_id)

    with session_factory() as db:
        with pytest.raises(ConflictException) as duplicated:
            WorkspaceService(WorkspaceRepository(db)).add_workspace(
                WorkspaceCreate(name="Outra", slug="plataforma"), owner_id
            )
        assert duplicated.value.exception_data.error_code == "WORKSPACE_ALREADY_EXISTS"
        assert str(duplicated.value) == "Já existe um workspace com este slug"

    assert _count(session_factory, Workspace) == 1
    assert _count(session_factory, WorkspaceMember) == 1


def test_add_workspace_organization_codes_preserved(
    session_factory: sessionmaker[Session],
) -> None:
    owner_id = make_user(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0]).id

    with session_factory() as db:
        with pytest.raises(NotFoundException) as missing:
            WorkspaceService(WorkspaceRepository(db)).add_workspace(
                WorkspaceCreate(name="Plataforma", slug="plataforma"), owner_id
            )
        assert missing.value.exception_data.error_code == "ORGANIZATION_NOT_FOUND"

    other_id = make_user(session_factory, email="bia@ressonant.dev", cpf=VALID_CPFS[1]).id
    foreign_org = _seed_org(session_factory, other_id, "org-bia")
    with session_factory() as db:
        with pytest.raises(ForbiddenException) as forbidden:
            WorkspaceService(WorkspaceRepository(db)).add_workspace(
                WorkspaceCreate(name="Plataforma", slug="plataforma", organization_id=foreign_org),
                owner_id,
            )
        assert forbidden.value.exception_data.error_code == "ORGANIZATION_FORBIDDEN"

    _seed_org(session_factory, owner_id, "org-uma")
    _seed_org(session_factory, owner_id, "org-duas")
    with session_factory() as db:
        with pytest.raises(ConflictException) as ambiguous:
            WorkspaceService(WorkspaceRepository(db)).add_workspace(
                WorkspaceCreate(name="Plataforma", slug="plataforma"), owner_id
            )
        assert ambiguous.value.exception_data.error_code == "ORGANIZATION_AMBIGUOUS"

    assert _count(session_factory, Workspace) == 0
    assert _count(session_factory, WorkspaceMember) == 0


def test_add_team_stages_without_commit(session_factory: sessionmaker[Session]) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)

    with session_factory() as db:
        team = TeamService(TeamRepository(db)).add_team(
            TeamCreate(name="Time A", slug="time-a", workspace_id=workspace_id), owner_id
        )
        assert team.key_prefix == "TIMEA"
        assert db.in_transaction()
        assert _count_in(db, Team) == 1
        assert _count_in(db, TeamMember) == 1
        member = db.scalar(select(TeamMember).where(TeamMember.team_id == team.id))
        assert member is not None
        assert member.user_id == owner_id
        assert member.role == "admin"

    assert _count(session_factory, Team) == 0
    assert _count(session_factory, TeamMember) == 0

    with session_factory() as db:
        TeamService(TeamRepository(db)).add_team(
            TeamCreate(name="Time B", slug="time-b", workspace_id=workspace_id), owner_id
        )
        db.commit()

    assert _count(session_factory, Team) == 1
    assert _count(session_factory, TeamMember) == 1


def test_team_create_commits(session_factory: sessionmaker[Session]) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)

    with session_factory() as db:
        team = TeamService(TeamRepository(db)).create(
            TeamCreate(name="Time A", slug="time-a", workspace_id=workspace_id), owner_id
        )
        assert team.id

    assert _count(session_factory, Team) == 1
    assert _count(session_factory, TeamMember) == 1


def test_add_team_duplicate_slug_and_non_member_keep_codes(
    session_factory: sessionmaker[Session],
) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)
    with session_factory() as db:
        TeamService(TeamRepository(db)).create(
            TeamCreate(name="Time A", slug="time-a", workspace_id=workspace_id), owner_id
        )

    with session_factory() as db:
        with pytest.raises(ConflictException) as duplicated:
            TeamService(TeamRepository(db)).add_team(
                TeamCreate(name="Time B", slug="time-a", workspace_id=workspace_id), owner_id
            )
        assert duplicated.value.exception_data.error_code == "TEAM_ALREADY_EXISTS"
        assert str(duplicated.value) == "Já existe um team com este slug"

    outsider = make_user(session_factory, email="bia@ressonant.dev", cpf=VALID_CPFS[1])
    with session_factory() as db:
        with pytest.raises(ForbiddenException) as forbidden:
            TeamService(TeamRepository(db)).add_team(
                TeamCreate(name="Time C", slug="time-c", workspace_id=workspace_id),
                outsider.id,
            )
        assert forbidden.value.exception_data.error_code == "FORBIDDEN"

    assert _count(session_factory, Team) == 1
    assert _count(session_factory, TeamMember) == 1


def test_add_team_allocates_distinct_key_prefixes(session_factory: sessionmaker[Session]) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)

    with session_factory() as db:
        service = TeamService(TeamRepository(db))
        first = service.add_team(
            TeamCreate(name="Time A", slug="team-a", workspace_id=workspace_id), owner_id
        )
        second = service.add_team(
            TeamCreate(name="Time B", slug="team_a", workspace_id=workspace_id), owner_id
        )
        assert [first.key_prefix, second.key_prefix] == ["TEAMA", "TEAMA2"]
        db.commit()

    with session_factory() as db:
        prefixes = list(
            db.scalars(
                select(Team.key_prefix).where(Team.workspace_id == workspace_id).order_by(Team.slug)
            )
        )
    assert prefixes == ["TEAMA", "TEAMA2"]


def test_team_key_prefix_conflict_rolls_back_without_orphan(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)

    def raise_unique_violation(repository: TeamRepository, team: Team) -> Team:
        raise IntegrityError(
            "INSERT INTO teams",
            {"workspace_id": team.workspace_id, "key_prefix": team.key_prefix},
            Exception("uq_teams_workspace_key_prefix"),
        )

    monkeypatch.setattr(TeamRepository, "add", raise_unique_violation)
    with session_factory() as db:
        with pytest.raises(ConflictException) as conflict:
            TeamService(TeamRepository(db)).create(
                TeamCreate(name="Time Race", slug="time-race", workspace_id=workspace_id),
                owner_id,
            )
        assert conflict.value.exception_data.error_code == "TEAM_KEY_PREFIX_CONFLICT"
        assert str(conflict.value) == "Prefixo de chave do team já está em uso neste workspace"
        assert _count_in(db, Team) == 0
        assert _count_in(db, TeamMember) == 0

    assert _count(session_factory, Team) == 0
    assert _count(session_factory, TeamMember) == 0


def test_workspace_create_rolls_back_without_orphan(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])

    def fail_member(repository: WorkspaceRepository, member: WorkspaceMember) -> WorkspaceMember:
        raise RuntimeError("falha ao gravar membro")

    monkeypatch.setattr(WorkspaceRepository, "add_member", fail_member)
    with session_factory() as db:
        with pytest.raises(RuntimeError, match="falha ao gravar membro"):
            WorkspaceService(WorkspaceRepository(db)).create(
                WorkspaceCreate(name="Plataforma", slug="plataforma"), owner_id
            )
        assert _count_in(db, Workspace) == 0
        assert _count_in(db, WorkspaceMember) == 0

    assert _count(session_factory, Workspace) == 0
    assert _count(session_factory, WorkspaceMember) == 0


def test_team_create_rolls_back_without_orphan(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = _seed_owner(session_factory, email="ana@ressonant.dev", cpf=VALID_CPFS[0])
    workspace_id = _seed_workspace(session_factory, owner_id)

    def fail_member(repository: TeamRepository, member: TeamMember) -> TeamMember:
        raise RuntimeError("falha ao gravar membro")

    monkeypatch.setattr(TeamRepository, "add_member", fail_member)
    with session_factory() as db:
        with pytest.raises(RuntimeError, match="falha ao gravar membro"):
            TeamService(TeamRepository(db)).create(
                TeamCreate(name="Time A", slug="time-a", workspace_id=workspace_id), owner_id
            )
        assert _count_in(db, Team) == 0
        assert _count_in(db, TeamMember) == 0

    assert _count(session_factory, Team) == 0
    assert _count(session_factory, TeamMember) == 0
