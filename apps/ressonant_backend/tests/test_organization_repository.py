"""Testes do repositório de organizações, sem API."""

from datetime import datetime

import pytest
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.models import Organization, OrganizationMember
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import VALID_CPFS, make_user


def _seed_with_owner(
    session_factory: sessionmaker[Session],
    user_id: str,
    slug: str,
    *,
    member_created_at: datetime | None = None,
) -> str:
    """Cria organização com membership de owner ativa usando o próprio repositório."""
    with session_factory() as db:
        repository = OrganizationRepository(db)
        organization = repository.add(Organization(name=f"Org {slug}", slug=slug))
        member = OrganizationMember(
            organization_id=organization.id,
            user_id=user_id,
            role="owner",
            status="active",
        )
        if member_created_at is not None:
            member.criado_em = member_created_at
        repository.add_member(member)
        db.commit()
        return organization.id


def test_add_member_and_get_by_id_and_slug(session_factory: sessionmaker[Session]) -> None:
    user = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])

    with session_factory() as db:
        repository = OrganizationRepository(db)
        organization = repository.add(Organization(name="Org Alfa", slug="org-alfa"))
        repository.add_member(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        db.commit()

    with session_factory() as db:
        repository = OrganizationRepository(db)
        by_id = repository.get_by_id(organization.id)
        by_slug = repository.get_by_slug("org-alfa")
        assert by_id is not None
        assert by_slug is not None
        assert by_id.id == by_slug.id == organization.id
        assert by_slug.name == "Org Alfa"
        assert repository.get_by_id("nao-e-uuid") is None
        assert repository.get_by_slug("org-inexistente") is None


def test_exists_by_slug(session_factory: sessionmaker[Session]) -> None:
    user = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])
    _seed_with_owner(session_factory, user.id, "org-existe")

    with session_factory() as db:
        repository = OrganizationRepository(db)
        assert repository.exists_by_slug("org-existe") is True
        assert repository.exists_by_slug("org-nao-existe") is False


def test_list_members(session_factory: sessionmaker[Session]) -> None:
    owner = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])
    regular = make_user(session_factory, email="member@example.com", cpf=VALID_CPFS[1])
    organization_id = _seed_with_owner(session_factory, owner.id, "org-membros")

    with session_factory() as db:
        repository = OrganizationRepository(db)
        repository.add_member(
            OrganizationMember(
                organization_id=organization_id,
                user_id=regular.id,
                role="member",
                status="active",
            )
        )
        db.commit()

    with session_factory() as db:
        repository = OrganizationRepository(db)
        members = repository.list_members(organization_id)
        assert {member.user_id: member.role for member in members} == {
            owner.id: "owner",
            regular.id: "member",
        }
        assert repository.list_members("nao-e-uuid") == []


def test_list_for_user(session_factory: sessionmaker[Session]) -> None:
    owner = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])
    other = make_user(session_factory, email="other@example.com", cpf=VALID_CPFS[1])
    recent_id = _seed_with_owner(
        session_factory,
        owner.id,
        "org-recente",
        member_created_at=datetime(2026, 2, 1),
    )
    older_id = _seed_with_owner(
        session_factory,
        owner.id,
        "org-antiga",
        member_created_at=datetime(2026, 1, 1),
    )
    tied_id = _seed_with_owner(
        session_factory,
        owner.id,
        "org-empate",
        member_created_at=datetime(2026, 1, 1),
    )
    _seed_with_owner(session_factory, other.id, "org-alheia")

    with session_factory() as db:
        repository = OrganizationRepository(db)
        rows = repository.list_for_user(owner.id)
        first_id, second_id = sorted((older_id, tied_id))
        assert [organization.id for organization, _ in rows] == [first_id, second_id, recent_id]
        assert all(member.user_id == owner.id for _, member in rows)
        assert repository.list_for_user("nao-e-uuid") == []


def test_duplicate_slug_raises_integrity_error(session_factory: sessionmaker[Session]) -> None:
    user = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])
    first_id = _seed_with_owner(session_factory, user.id, "org-unica")

    with session_factory() as db:
        repository = OrganizationRepository(db)
        with pytest.raises(IntegrityError):
            repository.add(Organization(name="Duplicada", slug="org-unica"))
        db.rollback()

    with session_factory() as db:
        repository = OrganizationRepository(db)
        found = repository.get_by_slug("org-unica")
        assert found is not None
        assert found.id == first_id
        assert db.scalar(select(func.count()).select_from(Organization)) == 1


def test_add_and_add_member_do_not_commit(session_factory: sessionmaker[Session]) -> None:
    user = make_user(session_factory, email="owner@example.com", cpf=VALID_CPFS[0])
    slug = "org-sem-commit"

    with session_factory() as db:
        repository = OrganizationRepository(db)
        organization = repository.add(Organization(name="Sem commit", slug=slug))
        repository.add_member(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        assert db.in_transaction() is True

    # StaticPool compartilha a conexão: só após fechar (rollback implícito) outra
    # Session reflete o que realmente foi confirmado no banco.
    with session_factory() as other:
        other_repository = OrganizationRepository(other)
        assert other_repository.get_by_slug(slug) is None
        assert other.scalar(select(func.count()).select_from(OrganizationMember)) == 0

    with session_factory() as db:
        repository = OrganizationRepository(db)
        committed = repository.add(Organization(name="Com commit", slug=slug))
        repository.add_member(
            OrganizationMember(
                organization_id=committed.id,
                user_id=user.id,
                role="owner",
                status="active",
            )
        )
        db.commit()

    with session_factory() as other:
        other_repository = OrganizationRepository(other)
        assert other_repository.get_by_slug(slug) is not None
        assert len(other_repository.list_members(committed.id)) == 1
