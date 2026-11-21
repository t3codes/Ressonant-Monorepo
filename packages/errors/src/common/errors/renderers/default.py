from typing import Any

from common.errors.common_codes import CommonErrorCode
from common.errors.exceptions import ApplicationException
from common.errors.renderers.helpers import (
    build_trace_reference_detail,
    get_error_code,
    get_trace_id,
)
from common.errors.renderers.schemas import ErrorSchema
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException


class DefaultErrorRenderer:
    """Contrato de erro padrão do monorepo: o `ErrorSchema` de `common.errors`."""

    def render(self, exc: ApplicationException) -> tuple[int, Any]:
        data = exc.exception_data
        return exc.status_code, ErrorSchema(
            status_code=exc.status_code,
            message=data.message,
            detail=data.detail,
            error_code=data.error_code,
            error_messages=data.error_messages,
            error_layer=data.error_layer,
            required_capability=data.required_capability,
            correlation_id=data.correlation_id or get_trace_id(),
        )

    def render_http(self, exc: StarletteHTTPException) -> tuple[int, Any]:
        return exc.status_code, ErrorSchema(
            status_code=exc.status_code,
            message="The request is invalid or cannot be served",
            detail=build_trace_reference_detail(),
            error_code=get_error_code(exc.status_code),
            error_messages=[{"detail": str(exc.detail)}] if exc.detail else None,
            correlation_id=get_trace_id(),
        )

    def render_validation(self, exc: RequestValidationError) -> tuple[int, Any]:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        return status_code, ErrorSchema(
            status_code=status_code,
            message="Validation failed for the provided payload",
            detail=build_trace_reference_detail(),
            error_code=get_error_code(status_code),
            error_messages=[
                {"loc": err["loc"], "msg": err["msg"], "type": err["type"]} for err in exc.errors()
            ],
            correlation_id=get_trace_id(),
        )

    def render_pydantic_validation(self, exc: ValidationError) -> tuple[int, Any]:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        return status_code, ErrorSchema(
            status_code=status_code,
            message="The request is invalid or validation failed for the provided payload",
            detail=build_trace_reference_detail(),
            error_code=get_error_code(status_code),
            error_messages=[{"msg": err["msg"]} for err in exc.errors()],
            correlation_id=get_trace_id(),
        )

    def render_unhandled(self, exc: Exception) -> tuple[int, Any]:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return status_code, ErrorSchema(
            status_code=status_code,
            message="An unexpected internal error occurred",
            detail=build_trace_reference_detail(),
            error_code=CommonErrorCode.UNEXPECTED_ERROR,
            correlation_id=get_trace_id(),
        )
