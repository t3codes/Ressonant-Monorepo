from typing import Any, Protocol

from common.errors.exceptions import ApplicationException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorRenderer(Protocol):
    """Converte uma exceção no corpo da resposta de erro.

    Cada método devolve `(status_code, body)`; o handler cuida de log e transporte.
    Aplicações com contrato próprio herdam de `DefaultErrorRenderer` e sobrescrevem
    apenas os métodos que mudam.
    """

    # A própria aplicação levantou um erro de negócio.
    def render(self, exc: ApplicationException) -> tuple[int, Any]: ...

    # O Starlette abortou a request: rota inexistente, método não permitido, auth sem header.
    def render_http(self, exc: StarletteHTTPException) -> tuple[int, Any]: ...

    # O FastAPI rejeitou a entrada da request: body, query, path ou header fora do schema.
    def render_validation(self, exc: RequestValidationError) -> tuple[int, Any]: ...

    # Um `model_validate` falhou fora do ciclo de validação da request.
    def render_pydantic_validation(self, exc: ValidationError) -> tuple[int, Any]: ...

    # Qualquer exceção não prevista escapou até o topo e vira 500.
    def render_unhandled(self, exc: Exception) -> tuple[int, Any]: ...
