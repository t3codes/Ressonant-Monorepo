import uuid

from app.modules.organization.domain.models import Organization, OrganizationMember
from sqlalchemy import select
from sqlalchemy.orm import Session


class OrganizationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, organization_id: str) -> Organization | None:
        try:
            uuid.UUID(organization_id)
        except ValueError:
            return None
        return self._db.get(Organization, organization_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        return self._db.scalar(select(Organization).where(Organization.slug == slug))

    def exists_by_slug(self, slug: str) -> bool:
        return (
            self._db.scalar(select(Organization.id).where(Organization.slug == slug).limit(1))
            is not None
        )

    def add(self, organization: Organization) -> Organization:
        self._db.add(organization)
        self._db.flush()
        return organization

    def add_member(self, member: OrganizationMember) -> OrganizationMember:
        self._db.add(member)
        self._db.flush()
        return member

    def list_members(self, organization_id: str) -> list[OrganizationMember]:
        try:
            uuid.UUID(organization_id)
        except ValueError:
            return []
        return list(
            self._db.scalars(
                select(OrganizationMember)
                .where(OrganizationMember.organization_id == organization_id)
                .order_by(OrganizationMember.criado_em, OrganizationMember.user_id)
            )
        )

    def list_for_user(self, user_id: str) -> list[tuple[Organization, OrganizationMember]]:
        """Memberships do usuário, da mais antiga para a mais recente."""
        try:
            uuid.UUID(user_id)
        except ValueError:
            return []
        stmt = (
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(OrganizationMember.criado_em, Organization.id)
        )
        return [(organization, member) for organization, member in self._db.execute(stmt)]

    def commit(self) -> None:
        """Só para consistência de padrão: o orquestrador atômico compartilha uma Session
        e fará um único commit no fim, portanto não deve chamar este método.
        """
        self._db.commit()

    def rollback(self) -> None:
        """Só para consistência de padrão: o orquestrador atômico compartilha uma Session
        e fará um único commit no fim, portanto não deve chamar este método.
        """
        self._db.rollback()
