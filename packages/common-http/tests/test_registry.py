import httpx
import pytest
import respx
from common.http import HttpClientConfig, HttpClientRegistry

BACKEND = "backend"
BACKEND_URL = "https://backend.test"
A_URL = "https://a.test"
UPSTREAM_URL = "https://upstream.test"


def _pool(client: httpx.AsyncClient):
    # O httpx não expõe os limites aplicados; o pool do httpcore é o único lugar para confirmá-los.
    return client._transport._pool  # type: ignore[attr-defined]


class TestRegister:
    def test_uses_base_url_and_default_config(self, registry: HttpClientRegistry) -> None:
        client = registry.register(BACKEND, base_url=BACKEND_URL)
        defaults = HttpClientConfig()

        assert client.base_url == httpx.URL(BACKEND_URL)
        assert client.timeout == httpx.Timeout(
            connect=defaults.connect_timeout,
            read=defaults.read_timeout,
            write=defaults.write_timeout,
            pool=defaults.pool_timeout,
        )
        assert _pool(client)._max_connections == defaults.max_connections
        assert _pool(client)._max_keepalive_connections == defaults.max_keepalive_connections
        assert _pool(client)._keepalive_expiry == defaults.keepalive_expiry

    def test_applies_given_config(self, registry: HttpClientRegistry) -> None:
        config = HttpClientConfig(
            connect_timeout=1,
            read_timeout=2,
            write_timeout=3,
            pool_timeout=4,
            max_connections=7,
            max_keepalive_connections=5,
            keepalive_expiry=1.5,
        )

        client = registry.register("auth", base_url="https://auth.test", config=config)

        assert client.timeout == httpx.Timeout(connect=1, read=2, write=3, pool=4)
        assert _pool(client)._max_connections == 7
        assert _pool(client)._max_keepalive_connections == 5
        assert _pool(client)._keepalive_expiry == pytest.approx(1.5)

    def test_clients_have_independent_configs(self, registry: HttpClientRegistry) -> None:
        fast = registry.register("fast", "https://fast.test", HttpClientConfig(read_timeout=1))
        slow = registry.register("slow", "https://slow.test", HttpClientConfig(read_timeout=60))

        assert fast.timeout.read == 1
        assert slow.timeout.read == 60

    def test_duplicate_name_raises(self, registry: HttpClientRegistry) -> None:
        registry.register(BACKEND, base_url=BACKEND_URL)

        with pytest.raises(ValueError, match="já registrado"):
            registry.register(BACKEND, base_url="https://other.test")

    @pytest.mark.asyncio
    @respx.mock
    async def test_set_cookie_from_upstream_is_not_kept_between_requests(
        self, registry: HttpClientRegistry
    ) -> None:
        respx.get(f"{UPSTREAM_URL}/login").mock(
            return_value=httpx.Response(200, headers={"set-cookie": "session=abc; Path=/"})
        )
        me = respx.get(f"{UPSTREAM_URL}/me").mock(return_value=httpx.Response(200))

        # Controle: um client comum guardaria o cookie, o que provaria o vazamento entre usuários.
        async with httpx.AsyncClient(base_url=UPSTREAM_URL) as plain:
            await plain.get("/login")
            await plain.get("/me")
        assert me.calls.last.request.headers.get("cookie") == "session=abc"

        shared = registry.register("upstream", base_url=UPSTREAM_URL)
        await shared.get("/login")
        await shared.get("/me")

        assert "cookie" not in me.calls.last.request.headers


class TestGet:
    def test_returns_the_registered_client(self, registry: HttpClientRegistry) -> None:
        client = registry.register(BACKEND, base_url=BACKEND_URL)

        assert registry.get(BACKEND) is client

    def test_unknown_name_raises_key_error(self, registry: HttpClientRegistry) -> None:
        with pytest.raises(KeyError, match="não registrado"):
            registry.get("missing")


class TestAclose:
    @pytest.mark.asyncio
    async def test_closes_every_client_and_empties_registry(self) -> None:
        registry = HttpClientRegistry()
        first = registry.register("a", base_url=A_URL)
        second = registry.register("b", base_url="https://b.test")

        await registry.aclose()

        assert first.is_closed and second.is_closed
        with pytest.raises(KeyError):
            registry.get("a")

    @pytest.mark.asyncio
    async def test_is_idempotent(self) -> None:
        registry = HttpClientRegistry()
        registry.register("a", base_url=A_URL)

        await registry.aclose()
        await registry.aclose()

    @pytest.mark.asyncio
    async def test_name_can_be_registered_again_afterwards(self) -> None:
        registry = HttpClientRegistry()
        registry.register("a", base_url=A_URL)
        await registry.aclose()

        client = registry.register("a", base_url=A_URL)

        assert not client.is_closed
        await registry.aclose()

    @pytest.mark.asyncio
    async def test_keeps_closing_after_a_failure_and_reports_every_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = HttpClientRegistry()
        failing_first = registry.register("failing-first", base_url=A_URL)
        healthy = registry.register("healthy", base_url="https://b.test")
        failing_last = registry.register("failing-last", base_url="https://c.test")

        async def _fail(self: httpx.AsyncClient) -> None:
            raise RuntimeError(f"boom {self.base_url.host}")

        monkeypatch.setattr(failing_first, "aclose", _fail.__get__(failing_first))
        monkeypatch.setattr(failing_last, "aclose", _fail.__get__(failing_last))

        with pytest.raises(ExceptionGroup) as exc_info:
            await registry.aclose()

        assert healthy.is_closed
        assert [str(error) for error in exc_info.value.exceptions] == ["boom a.test", "boom c.test"]
        with pytest.raises(KeyError):
            registry.get("healthy")
