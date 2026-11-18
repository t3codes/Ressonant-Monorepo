from dataclasses import asdict
from http import HTTPStatus
from typing import ClassVar

from common.errors.common_codes import CommonErrorCode
from common.errors.exception_data import ExceptionData
from fastapi import status


class ApplicationException(Exception):
    """Base das exceções de aplicação.

    A subclasse fixa o status HTTP em `default_status_code`.
    O `error_code` é derivado do nome desse status quando o chamador não informa um.
    `default_error_code` só é necessário quando o código não acompanha o status.

        class NotFoundException(ApplicationException):
            default_status_code = 404       # error_code -> "NOT_FOUND"

    `is_expected` marca um erro como resultado normal do endpoint, não uma falha a
    investigar — o exception handler deixa de logá-lo como ERROR. Default `False`:
    o status HTTP (nem 4xx) não rebaixa o log sozinho, só o código que levanta a
    exceção sabe se aquele erro é realmente esperado.
    """

    default_status_code: ClassVar[int | None] = None
    default_error_code: ClassVar[str | None] = None

    def __init__(
        self,
        exception_data: ExceptionData,
        status_code: int | None = None,
        is_expected: bool = False,
    ):
        resolved_status_code = status_code if status_code is not None else self.default_status_code

        if resolved_status_code is None:
            raise ValueError("status_code is required for exceptions without a default_status_code")

        if resolved_status_code < 400:
            raise ValueError(
                "status_code must be a client (4xx) or server (5xx) error code, "
                f"got {resolved_status_code}"
            )

        if self.default_status_code is not None and exception_data.error_code is None:
            exception_data.error_code = (
                self.default_error_code or HTTPStatus(resolved_status_code).name
            )

        self.exception_data = exception_data
        self.status_code = resolved_status_code
        self.is_expected = is_expected

        super().__init__(exception_data.message)

    def to_dict(self) -> dict:
        return asdict(self.exception_data)


class BadRequestException(ApplicationException):
    default_status_code = status.HTTP_400_BAD_REQUEST


class UnauthorizedException(ApplicationException):
    default_status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenException(ApplicationException):
    default_status_code = status.HTTP_403_FORBIDDEN


class NotFoundException(ApplicationException):
    default_status_code = status.HTTP_404_NOT_FOUND


class UnexpectedException(ApplicationException):
    default_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class HttpIntegrationException(ApplicationException):
    default_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_error_code = CommonErrorCode.HTTP_INTEGRATION_ERROR
