from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus

import httpx


class FailureKind(StrEnum):
    STATUS = "status"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class UpstreamFailure:
    """O que deu errado numa chamada a um serviço externo.

    Não tem o formato de erro de nenhuma app: a app decide, em `build_error`, qual exceção criar.

    - `kind`: `STATUS` (o upstream respondeu com erro), `TIMEOUT` (sem resposta a tempo),
      `TRANSPORT` (falha de rede ou do pool de conexões) ou `INVALID_RESPONSE` (o corpo não
      segue o contrato).
    - `status_code`: o status que a app deve responder. É o do upstream em `STATUS`; 504 em
      `TIMEOUT`; 500 em `TRANSPORT`; 502 em `INVALID_RESPONSE` e quando o upstream responde 3xx.
    - `body`: corpo da resposta lido como objeto JSON; `{}` sem resposta ou se não for um objeto.
    - `text`: corpo da resposta como texto; `""` sem resposta.
    - `cause`: a exceção original.
    """

    kind: FailureKind
    operation: str
    status_code: int
    body: dict
    text: str
    cause: Exception


class InvalidUpstreamResponse(Exception):
    def __init__(self, response: httpx.Response, error: Exception) -> None:
        super().__init__(f"invalid response body: {error}")
        self.response = response


@asynccontextmanager
async def translate_http_errors(
    operation: str, build_error: Callable[[UpstreamFailure], Exception]
) -> AsyncIterator[None]:
    """Converte as falhas do `httpx` e de `validate_response` na exceção que `build_error` devolver.

    Envolva a chamada ao upstream, inclusive o `raise_for_status()` e a leitura do corpo.
    """
    try:
        yield
    except httpx.HTTPStatusError as exc:
        response = exc.response
        status_code = response.status_code if response.is_error else HTTPStatus.BAD_GATEWAY
        raise build_error(
            _failure(FailureKind.STATUS, operation, status_code, exc, response)
        ) from exc
    except InvalidUpstreamResponse as exc:
        failure = _failure(
            FailureKind.INVALID_RESPONSE, operation, HTTPStatus.BAD_GATEWAY, exc, exc.response
        )
        raise build_error(failure) from exc
    except httpx.PoolTimeout as exc:
        raise build_error(_failure(FailureKind.TRANSPORT, operation, 500, exc)) from exc
    except httpx.TimeoutException as exc:
        failure = _failure(FailureKind.TIMEOUT, operation, HTTPStatus.GATEWAY_TIMEOUT, exc)
        raise build_error(failure) from exc
    except httpx.HTTPError as exc:
        raise build_error(_failure(FailureKind.TRANSPORT, operation, 500, exc)) from exc


def validate_response[T](response: httpx.Response, parse: Callable[[bytes], T]) -> T:
    """Converte o corpo com `parse`; um `ValueError` de `parse` torna a resposta inválida.

    O `validate_json` de um `pydantic.TypeAdapter` já levanta `ValueError` para JSON malformado
    e para corpo fora do contrato.
    """
    try:
        return parse(response.content)
    except ValueError as exc:
        raise InvalidUpstreamResponse(response, exc) from exc


def _failure(
    kind: FailureKind,
    operation: str,
    status_code: int,
    cause: Exception,
    response: httpx.Response | None = None,
) -> UpstreamFailure:
    return UpstreamFailure(
        kind=kind,
        operation=operation,
        status_code=int(status_code),
        body=_json_object(response) if response is not None else {},
        text=response.text if response is not None else "",
        cause=cause,
    )


def _json_object(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
