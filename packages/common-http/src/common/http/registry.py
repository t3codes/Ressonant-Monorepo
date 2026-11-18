from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx
from common.http.config import HttpClientConfig


class HttpClientRegistry:
    """Um `httpx.AsyncClient` por nome, criado no lifespan e fechado no shutdown."""

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}

    def register(
        self, name: str, base_url: str, config: HttpClientConfig = HttpClientConfig()
    ) -> httpx.AsyncClient:
        if name in self._clients:
            raise ValueError(f"HTTP client {name!r} já registrado")
        client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=config.connect_timeout,
                read=config.read_timeout,
                write=config.write_timeout,
                pool=config.pool_timeout,
            ),
            limits=httpx.Limits(
                max_connections=config.max_connections,
                max_keepalive_connections=config.max_keepalive_connections,
                keepalive_expiry=config.keepalive_expiry,
            ),
            # Client compartilhado entre usuários: a policy vazia impede que um Set-Cookie
            # (ex.: Keycloak) seja guardado e reenviado a outro usuário.
            cookies=CookieJar(DefaultCookiePolicy(allowed_domains=[])),
        )
        self._clients[name] = client
        return client

    def get(self, name: str) -> httpx.AsyncClient:
        try:
            return self._clients[name]
        except KeyError:
            raise KeyError(f"HTTP client {name!r} não registrado") from None

    async def aclose(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        errors: list[Exception] = []
        for client in clients:
            try:
                await client.aclose()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("falha ao fechar clients HTTP", errors)
