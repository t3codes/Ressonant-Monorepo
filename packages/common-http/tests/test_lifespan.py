import pytest
from common.http import HttpClientRegistry, http_clients_lifespan
from fastapi import FastAPI

BACKEND = "backend"
BACKEND_URL = "https://backend.test"


class TestHttpClientsLifespan:
    @pytest.mark.asyncio
    async def test_exposes_registry_in_app_state_and_closes_it_on_exit(self) -> None:
        app = FastAPI()
        registry = HttpClientRegistry()
        client = registry.register(BACKEND, base_url=BACKEND_URL)

        async with http_clients_lifespan(app, registry) as yielded:
            assert yielded is registry
            assert app.state.http_clients is registry
            assert not client.is_closed

        assert client.is_closed

    @pytest.mark.asyncio
    async def test_closes_clients_when_the_app_fails(self) -> None:
        app = FastAPI()
        registry = HttpClientRegistry()
        client = registry.register(BACKEND, base_url=BACKEND_URL)

        with pytest.raises(RuntimeError):
            async with http_clients_lifespan(app, registry):
                raise RuntimeError("falha no startup")

        assert client.is_closed
