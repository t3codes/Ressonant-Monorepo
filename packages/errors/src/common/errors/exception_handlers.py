from collections.abc import Iterable, Mapping
from typing import Any

import structlog
from common.errors.exceptions import ApplicationException
from common.errors.renderers.default import DefaultErrorRenderer
from common.errors.renderers.helpers import get_trace_id
from common.errors.renderers.protocol import ErrorRenderer
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)

# Pydantic v2 anexa o `input` bruto (e `ctx`) a cada erro de validação. Logar os
# dicts inteiros gravaria senha, CPF e outros dados pessoais no log (AGENTS.md §3).
_SAFE_VALIDATION_FIELDS = ("type", "loc", "msg")


def _validation_errors_for_log(errors: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {field: error[field] for field in _SAFE_VALIDATION_FIELDS if field in error}
        for error in errors
    ]


def _to_response(rendered: tuple[int, Any]) -> JSONResponse:
    status_code, body = rendered
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


def _constraint_name(exc: Exception) -> str | None:
    """Nome da constraint violada, sem importar SQLAlchemy na lib (CYB-001).

    Acesso estritamente por atributo: `exc.orig.diag.constraint_name` existe em
    erros psycopg2. Nunca lemos `str(exc)`/`exc.orig` em log — o SQLAlchemy
    renderiza os parâmetros vinculados (senha, CPF, e-mail) na mensagem.
    """
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return str(name) if name else None


def _safe_exception_fields(exc: Exception) -> dict[str, Any]:
    # `exception` e `exc_info=False` são explícitos: o processador
    # `extract_exception_info` do common.logs injeta o traceback corrente em
    # todo log de nível error, mesmo sem exc_info=True. Informar o campo
    # `exception` (com o tipo, nunca a mensagem) desativa essa injeção e evita
    # que CPF/e-mail/hash Argon2id dos parâmetros do SQL cheguem ao stdout.
    fields: dict[str, Any] = {
        "exception": type(exc).__name__,
        "correlation_id": get_trace_id(),
        "exc_info": False,
    }
    constraint = _constraint_name(exc)
    if constraint:
        fields["constraint_name"] = constraint
    return fields


def setup_exception_handlers(app, renderer: ErrorRenderer | None = None):
    resolved_renderer = renderer if renderer is not None else DefaultErrorRenderer()
    logger.info("exception_handlers.renderer.resolved", renderer=type(resolved_renderer).__name__)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # CYB-001: só tipo, correlation_id e constraint — nunca str(exc) nem
        # exc_info, cujos tracebacks carregam os parâmetros vinculados do SQL.
        logger.error("unhandled.exception", **_safe_exception_fields(exc))
        return _to_response(resolved_renderer.render_unhandled(exc))

    @app.exception_handler(ApplicationException)
    async def application_exception_handler(
        request: Request, exc: ApplicationException
    ) -> JSONResponse:
        if not exc.is_expected:
            fields = _safe_exception_fields(exc)
            fields["error_code"] = exc.exception_data.error_code
            logger.error("application.exception", **fields)
        return _to_response(resolved_renderer.render(exc))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        fields = _safe_exception_fields(exc)
        fields["status_code"] = exc.status_code
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            logger.warning("http.exception", **fields)
        else:
            logger.error("http.exception", **fields)
        return _to_response(resolved_renderer.render_http(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # CYB-001: `warning` sem `exc_info`. O traceback do Pydantic carrega o `input`
        # bruto (senha, CPF) e o `format_exc_info` do common-logs o renderizaria no
        # campo `exception`; `extract_exception_info` só anexa traceback em `error`.
        logger.warning(
            "validation.request.rejected",
            errors=_validation_errors_for_log(exc.errors()),
        )
        return _to_response(resolved_renderer.render_validation(exc))

    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
        # `str(exc)` também traz `input_value=`; use os campos seguros (ver CYB-001).
        logger.warning(
            "validation.model.rejected",
            errors=_validation_errors_for_log(exc.errors()),
        )
        return _to_response(resolved_renderer.render_pydantic_validation(exc))

    logger.debug("exception_handlers.setup.completed")
