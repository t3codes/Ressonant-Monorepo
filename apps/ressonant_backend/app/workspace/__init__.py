"""Compatibilidade: re-exporta do novo layout modular."""

from app.modules.workspace.dataproviders.repository import WorkspaceRepository  # noqa: F401
from app.modules.workspace.deps import get_workspace_repository, get_workspace_service  # noqa: F401
from app.modules.workspace.domain.models import (  # noqa: F401
    Workspace,
    WorkspaceMember,
)
from app.modules.workspace.entrypoints.routes import router  # noqa: F401
from app.modules.workspace.schemas.dto import (  # noqa: F401
    WorkspaceCreate,
    WorkspaceList,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceStatusUpdate,
    WorkspaceUpdate,
)
from app.modules.workspace.usecases.services import WorkspaceService  # noqa: F401
