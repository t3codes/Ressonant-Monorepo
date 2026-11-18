from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from common.http import HttpClientRegistry, http_client, http_clients_lifespan
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

BACKEND = "backend"
AUTH = "auth"
BACKEND_URL = "https://backend.test"
AUTH_URL = "https://auth.test"
FAKE_URL = "https://fake.test"

BackendClient = Annotated[httpx.AsyncClient, Depends(http_client(BACKEND))]


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = HttpClientRegistry()
        registry.register(BACKEND, base_url=BACKEND_URL)
        registry.register(AUTH, base_url=AUTH_URL)
        async with http_clients_lifespan(app, registry):
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/backend-url")
    async def backend_url(client: BackendClient) -> str:
        return str(client.base_url)

    @app.get("/auth-url")
    async def auth_url(client: Annotated[httpx.AsyncClient, Depends(http_client(AUTH))]) -> str:
        return str(client.base_url)

    return app


class TestHttpClientDependency:
    def test_same_name_returns_the_same_dependency(self) -> None:
        assert http_client(BACKEND) is http_client(BACKEND)
        assert http_client(BACKEND) is not http_client(AUTH)

    def test_dependency_resolves_the_client_registered_under_its_name(self) -> None:
        with TestClient(_build_app()) as test_client:
            assert test_client.get("/backend-url").json() == BACKEND_URL
            assert test_client.get("/auth-url").json() == AUTH_URL

    def test_dependency_can_be_overridden_by_name(self) -> None:
        app = _build_app()
        app.dependency_overrides[http_client(BACKEND)] = lambda: httpx.AsyncClient(
            base_url=FAKE_URL
        )

        with TestClient(app) as test_client:
            assert test_client.get("/backend-url").json() == FAKE_URL
            assert test_client.get("/auth-url").json() == AUTH_URL
