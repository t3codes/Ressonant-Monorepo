import uuid

from app.modules.teams.domain.models import Team, TeamMember
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


class TeamRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, team_id: str) -> Team | None:
        try:
            uuid.UUID(team_id)
        except ValueError:
            return None
        return self._db.get(Team, team_id)

    def get_by_slug(self, slug: str) -> Team | None:
        return self._db.scalar(select(Team).where(Team.slug == slug))

    def exists_by_slug(self, slug: str) -> bool:
        return self._db.scalar(select(Team.id).where(Team.slug == slug).limit(1)) is not None

    def list_key_prefixes(self, workspace_id: str) -> set[str]:
        """Prefixos já usados no workspace; a unicidade da constraint é por workspace."""
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return set()
        return set(
            self._db.scalars(select(Team.key_prefix).where(Team.workspace_id == workspace_id)).all()
        )

    def list_for_workspace(
        self,
        workspace_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_ativo: bool | None = None,
    ) -> tuple[list[Team], int]:
        """Teams de um workspace onde o usuário é membro."""
        try:
            uuid.UUID(workspace_id)
            uuid.UUID(user_id)
        except ValueError:
            return [], 0
        stmt = (
            select(Team)
            .join(
                TeamMember,
                TeamMember.team_id == Team.id,
                isouter=True,
            )
            .where(Team.workspace_id == workspace_id)
            .where(Team.is_deleted.is_(False))
            .where(or_(Team.owner_id == user_id, TeamMember.user_id == user_id))
            .distinct()
        )
        if status_ativo is not None:
            stmt = stmt.where(Team.status_ativo == status_ativo)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = self._db.scalars(stmt.order_by(Team.criado_em, Team.id).offset(skip).limit(limit))
        return list(items), total

    def list_members(self, team_id: str) -> list[TeamMember]:
        """Lista membros de um time."""
        try:
            uuid.UUID(team_id)
        except ValueError:
            return []
        return list(
            self._db.scalars(
                select(TeamMember)
                .where(TeamMember.team_id == team_id)
                .order_by(TeamMember.criado_em)
            )
        )

    def is_member(self, team_id: str, user_id: str) -> TeamMember | None:
        try:
            uuid.UUID(team_id)
            uuid.UUID(user_id)
        except ValueError:
            return None
        return self._db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )

    def add(self, team: Team) -> Team:
        self._db.add(team)
        self._db.flush()
        return team

    def add_member(self, member: TeamMember) -> TeamMember:
        self._db.add(member)
        self._db.flush()
        return member

    def get_member(self, team_id: str, user_id: str) -> TeamMember | None:
        return self.is_member(team_id, user_id)

    def get_default_for_workspace(self, workspace_id: str) -> Team | None:
        """Primeira equipe ativa do workspace (mais antiga) para onboarding por convite."""
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return None
        return self._db.scalar(
            select(Team)
            .where(
                Team.workspace_id == workspace_id,
                Team.status_ativo.is_(True),
                Team.is_deleted.is_(False),
            )
            .order_by(Team.criado_em, Team.id)
            .limit(1)
        )

    def remove_member(self, member: TeamMember) -> None:
        self._db.delete(member)
        self._db.flush()

    def list_deleted_for_workspace(self, workspace_id: str) -> list[Team]:
        try:
            uuid.UUID(workspace_id)
        except ValueError:
            return []
        return list(
            self._db.scalars(
                select(Team)
                .where(Team.workspace_id == workspace_id, Team.is_deleted.is_(True))
                .order_by(Team.deleted_at.desc(), Team.criado_em.desc())
            ).all()
        )

    def delete_team(self, team: Team) -> None:
        self._db.delete(team)
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
