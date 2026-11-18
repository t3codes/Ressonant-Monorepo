"""Compatibilidade: re-exporta do novo layout modular."""
from app.modules.teams.dataproviders.repository import TeamRepository  # noqa: F401
from app.modules.teams.deps import get_team_repository, get_team_service  # noqa: F401
from app.modules.teams.domain.models import Team, TeamMember  # noqa: F401
from app.modules.teams.entrypoints.routes import router  # noqa: F401
from app.modules.teams.schemas.dto import (  # noqa: F401
    TeamCreate,
    TeamList,
    TeamMemberAdd,
    TeamMemberResponse,
    TeamResponse,
    TeamStatusUpdate,
    TeamUpdate,
)
from app.modules.teams.usecases.services import TeamService  # noqa: F401
