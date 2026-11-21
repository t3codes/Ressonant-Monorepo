import os
from contextlib import asynccontextmanager
from typing import Annotated

if os.getenv("DD_TRACE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}:
    from common.datadog import initialize_datadog

    initialize_datadog()

from common.errors import setup_exception_handlers
from common.logs import setup_logging
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.engine import get_db
from app.modules.auth.entrypoints import routes as auth_routes
from app.modules.chat.domain.models import (  # noqa: F401  (registra as tabelas no metadata)
    Channel,
    Conversation,
    Message,
)
from app.modules.chat.entrypoints import conversation_router, message_router
from app.modules.chat.entrypoints import routes as chat_routes
from app.modules.chat.entrypoints import websocket as chat_websocket_routes
from app.modules.image_upload.entrypoints import routes as upload_routes  # noqa: F401
from app.modules.kanban_boards.domain.models import (  # noqa: F401  (registra as tabelas no metadata)
    Board,
    BoardColumn,
)
from app.modules.kanban_boards.entrypoints import routes as kanban_boards_routes
from app.modules.kanban_cards.domain.models import (
    Card,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.kanban_cards.entrypoints import routes as kanban_cards_routes
from app.modules.mail.domain.models import Email  # noqa: F401  (registra as tabelas no metadata)
from app.modules.mail.entrypoints import routes as mail_routes  # noqa: F401
from app.modules.notifications.domain.models import (
    AppNotification,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.notifications.entrypoints import routes as notifications_routes  # noqa: F401
from app.modules.organization.domain.models import (  # noqa: F401
    Invitation,
    Organization,
    OrganizationMember,
)
from app.modules.reactions.domain.models import (
    MessageReaction,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.reactions.entrypoints import routes as reactions_routes  # noqa: F401
from app.modules.readstates.domain.models import (
    ReadState,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.readstates.entrypoints import routes as readstates_routes  # noqa: F401
from app.modules.teams.domain.models import Team  # noqa: F401  (registra as tabelas no metadata)
from app.modules.teams.entrypoints import routes as teams_routes
from app.modules.user.domain.models import User  # noqa: F401  (registra as tabelas no metadata)
from app.modules.user.entrypoints import routes as user_routes
from app.modules.workspace.domain.models import (
    Workspace,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.workspace.entrypoints import routes as workspace_routes
from app.modules.workspace_management.domain.models import (  # noqa: F401
    AuditEvent,
    WorkspaceManagementGrant,
)
from app.modules.workspace_management.entrypoints import routes as workspace_management_routes


class HealthResponse(BaseModel):
    status: str
    service: str = "ressonant_backend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="Ressonant API",
        version="0.1.0",
        description="Autenticação e CRUD de usuários do Ressonant.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    setup_exception_handlers(app)
    app.include_router(auth_routes.router)
    app.include_router(user_routes.router)
    app.include_router(workspace_routes.router)
    app.include_router(workspace_management_routes.router)
    app.include_router(teams_routes.router)
    app.include_router(kanban_boards_routes.router)
    app.include_router(kanban_cards_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(chat_websocket_routes.router)
    app.include_router(conversation_router)
    app.include_router(message_router)
    app.include_router(reactions_routes.router)
    app.include_router(readstates_routes.router)
    app.include_router(notifications_routes.router)
    app.include_router(mail_routes.router)
    app.include_router(upload_routes.router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Liveness: o processo está de pé."""
        return HealthResponse(status="ok")

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    def ready(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
        """Readiness: o banco responde."""
        db.execute(text("SELECT 1"))
        return HealthResponse(status="ok")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))  # noqa: S104


if __name__ == "__main__":
    main()
