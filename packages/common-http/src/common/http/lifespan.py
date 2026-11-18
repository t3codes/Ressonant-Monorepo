from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common.http.registry import HttpClientRegistry
from fastapi import FastAPI


@asynccontextmanager
async def http_clients_lifespan(
    app: FastAPI, registry: HttpClientRegistry
) -> AsyncIterator[HttpClientRegistry]:
    app.state.http_clients = registry
    try:
        yield registry
    finally:
        await registry.aclose()
