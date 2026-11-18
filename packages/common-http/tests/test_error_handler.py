import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
import respx
from common.http import FailureKind, UpstreamFailure, translate_http_errors, validate_response
from common.http.error_handler import InvalidUpstreamResponse

UPSTREAM_URL = "https://upstream.test/things"
OPERATION = "get_thing"


class UpstreamError(Exception):
    def __init__(self, failure: UpstreamFailure) -> None:
        super().__init__(failure.kind)
        self.failure = failure


def _build_error(failure: UpstreamFailure) -> Exception:
    return UpstreamError(failure)


@pytest.fixture(autouse=True)
def _mock_transport() -> Iterator[None]:
    with respx.mock:
        yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def _get(client: httpx.AsyncClient, parse=json.loads):
    async with translate_http_errors(OPERATION, _build_error):
        response = await client.get(UPSTREAM_URL)
        response.raise_for_status()
        return validate_response(response, parse)


async def _failure_of(client: httpx.AsyncClient, parse=json.loads) -> UpstreamFailure:
    with pytest.raises(UpstreamError) as exc_info:
        await _get(client, parse)
    return exc_info.value.failure


@pytest.mark.asyncio
class TestTranslateHttpErrors:
    class TestSuccess:
        async def test_should_return_parsed_body_when_upstream_responds_ok(
            self, client: httpx.AsyncClient
        ) -> None:
            respx.get(UPSTREAM_URL).respond(200, json={"name": "a"})

            assert await _get(client) == {"name": "a"}

        async def test_should_not_wrap_errors_that_are_not_http_errors(
            self, client: httpx.AsyncClient
        ) -> None:
            with pytest.raises(KeyError):
                async with translate_http_errors(OPERATION, _build_error):
                    raise KeyError("x")

    class TestStatusErrors:
        @pytest.mark.parametrize("status_code", [400, 404, 422, 500, 503, 504])
        async def test_should_keep_upstream_status_when_upstream_responds_with_error(
            self, client: httpx.AsyncClient, status_code: int
        ) -> None:
            respx.get(UPSTREAM_URL).respond(status_code, json={"message": "boom"})

            failure = await _failure_of(client)

            assert failure.kind is FailureKind.STATUS
            assert failure.status_code == status_code
            assert failure.operation == OPERATION
            assert failure.body == {"message": "boom"}
            assert failure.text == '{"message":"boom"}'
            assert isinstance(failure.cause, httpx.HTTPStatusError)

        @pytest.mark.parametrize(
            "content", [b"<html>bad gateway</html>", b"", b"[1, 2]", b'"text"', b"null"]
        )
        async def test_should_return_empty_body_when_error_body_is_not_a_json_object(
            self, client: httpx.AsyncClient, content: bytes
        ) -> None:
            respx.get(UPSTREAM_URL).respond(502, content=content)

            failure = await _failure_of(client)

            assert failure.body == {}
            assert failure.text == content.decode()

        @pytest.mark.parametrize("status_code", [301, 302, 307])
        async def test_should_use_bad_gateway_when_upstream_responds_with_redirect(
            self, client: httpx.AsyncClient, status_code: int
        ) -> None:
            respx.get(UPSTREAM_URL).respond(status_code, headers={"location": "https://other.test"})

            failure = await _failure_of(client)

            assert failure.kind is FailureKind.STATUS
            assert failure.status_code == 502

    class TestTimeouts:
        @pytest.mark.parametrize(
            "error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout]
        )
        async def test_should_use_gateway_timeout_when_upstream_does_not_answer_in_time(
            self, client: httpx.AsyncClient, error: type[httpx.TimeoutException]
        ) -> None:
            respx.get(UPSTREAM_URL).mock(side_effect=error("slow"))

            failure = await _failure_of(client)

            assert failure.kind is FailureKind.TIMEOUT
            assert failure.status_code == 504
            assert failure.body == {}
            assert failure.text == ""
            assert isinstance(failure.cause, error)

    class TestTransportErrors:
        @pytest.mark.parametrize(
            "error",
            [httpx.PoolTimeout, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError],
        )
        async def test_should_use_internal_error_when_request_fails_before_a_response(
            self, client: httpx.AsyncClient, error: type[httpx.HTTPError]
        ) -> None:
            respx.get(UPSTREAM_URL).mock(side_effect=error("down"))

            failure = await _failure_of(client)

            assert failure.kind is FailureKind.TRANSPORT
            assert failure.status_code == 500
            assert isinstance(failure.cause, error)

    class TestInvalidResponses:
        @pytest.mark.parametrize("content", [b"not json", b"", b"<html></html>", b"\xff\xfe"])
        async def test_should_use_bad_gateway_when_success_body_is_not_json(
            self, client: httpx.AsyncClient, content: bytes
        ) -> None:
            respx.get(UPSTREAM_URL).respond(200, content=content)

            failure = await _failure_of(client)

            assert failure.kind is FailureKind.INVALID_RESPONSE
            assert failure.status_code == 502
            assert failure.body == {}
            assert failure.text == content.decode(errors="replace")
            assert isinstance(failure.cause, InvalidUpstreamResponse)

        async def test_should_not_translate_parse_errors_that_are_not_value_error(
            self, client: httpx.AsyncClient
        ) -> None:
            respx.get(UPSTREAM_URL).respond(200, json={"unexpected": True})

            with pytest.raises(KeyError):
                await _get(client, lambda content: json.loads(content)["name"])

        async def test_should_carry_the_object_body_when_parse_rejects_it(
            self, client: httpx.AsyncClient
        ) -> None:
            respx.get(UPSTREAM_URL).respond(200, json={"unexpected": True})

            def parse(content: bytes) -> str:
                raise ValueError("outside the contract")

            failure = await _failure_of(client, parse)

            assert failure.kind is FailureKind.INVALID_RESPONSE
            assert failure.body == {"unexpected": True}

    class TestBuildError:
        async def test_should_chain_original_error_as_cause_of_built_error(
            self, client: httpx.AsyncClient
        ) -> None:
            respx.get(UPSTREAM_URL).mock(side_effect=httpx.ReadTimeout("slow"))

            with pytest.raises(UpstreamError) as exc_info:
                await _get(client)

            assert exc_info.value.__cause__ is exc_info.value.failure.cause


class TestValidateResponse:
    def test_should_return_parsed_value_when_parse_succeeds(self) -> None:
        response = httpx.Response(200, content=b'{"a": 1}')

        assert validate_response(response, json.loads) == {"a": 1}

    def test_should_pass_raw_bytes_to_parse(self) -> None:
        response = httpx.Response(200, content=b"abc")

        assert validate_response(response, lambda content: content) == b"abc"

    def test_should_raise_invalid_upstream_response_when_parse_raises_value_error(
        self,
    ) -> None:
        response = httpx.Response(200, content=b"not json")

        with pytest.raises(InvalidUpstreamResponse) as exc_info:
            validate_response(response, json.loads)

        assert exc_info.value.response is response
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_should_not_swallow_errors_that_are_not_value_error(self) -> None:
        response = httpx.Response(200, content=b"{}")

        with pytest.raises(KeyError):
            validate_response(response, lambda content: json.loads(content)["x"])
