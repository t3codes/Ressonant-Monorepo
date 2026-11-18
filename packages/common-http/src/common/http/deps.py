from collections.abc import Callable
from functools import cache

import httpx
from fastapi import Request


@cache
def http_client(name: str) -> Callable[[Request], httpx.AsyncClient]:
    """Dependência FastAPI do client `name`. Cacheada por nome para que
    `app.dependency_overrides[http_client("x")]` use sempre a mesma chave."""

    def dependency(request: Request) -> httpx.AsyncClient:
        return request.app.state.http_clients.get(name)

    return dependency
