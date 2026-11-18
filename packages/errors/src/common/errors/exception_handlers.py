from collections.abc import Iterable, Mapping
from typing import Any

import structlog
from common.errors.exceptions import ApplicationException
from common.errors.renderers.default import DefaultErrorRenderer
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


def setup_exception_handlers(app, renderer: ErrorRenderer | None = None):
    resolved_renderer = renderer if renderer is not None else DefaultErrorRenderer()
    logger.info("exception_handlers.renderer.resolved", renderer=type(resolved_renderer).__name__)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled Exception", error=str(exc), exc_info=True)
        return _to_response(resolved_renderer.render_unhandled(exc))

    @app.exception_handler(ApplicationException)
    async def application_exception_handler(
        request: Request, exc: ApplicationException
    ) -> JSONResponse:
        if not exc.is_expected:
            logger.error(exc.to_dict(), exc_info=True)
        return _to_response(resolved_renderer.render(exc))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            logger.warning(str(exc))
        else:
            logger.error(str(exc), exc_info=True)
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
