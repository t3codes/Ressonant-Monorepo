import os
from contextlib import asynccontextmanager
from typing import Annotated

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
from app.modules.user.domain.models import User  # noqa: F401  (registra as tabelas no metadata)
from app.modules.user.entrypoints import routes as user_routes
from app.modules.workspace.domain.models import (
    Workspace,  # noqa: F401  (registra as tabelas no metadata)
)
from app.modules.workspace.entrypoints import routes as workspace_routes


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
