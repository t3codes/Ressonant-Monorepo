import dataclasses

import pytest
from common.http import HttpClientConfig

UVICORN_DEFAULT_KEEP_ALIVE_SECONDS = 5


class TestHttpClientConfig:
    def test_default_keepalive_expiry_is_below_uvicorn_idle_timeout(self) -> None:
        assert HttpClientConfig().keepalive_expiry < UVICORN_DEFAULT_KEEP_ALIVE_SECONDS

    def test_omitted_fields_keep_their_defaults(self) -> None:
        config = HttpClientConfig(read_timeout=10)

        assert config.read_timeout == 10
        assert config.connect_timeout == HttpClientConfig().connect_timeout
        assert config.max_connections == HttpClientConfig().max_connections

    def test_config_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            HttpClientConfig().read_timeout = 1  # type: ignore[misc]
