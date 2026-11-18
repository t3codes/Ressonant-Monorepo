from common.errors import ApplicationException, ExceptionData, UnauthorizedException
from fastapi import status


class ConflictException(ApplicationException):
    default_status_code = status.HTTP_409_CONFLICT


def invalid_credentials() -> UnauthorizedException:
    return UnauthorizedException(
        ExceptionData(message="Credenciais inválidas", error_code="INVALID_CREDENTIALS"),
        is_expected=True,
    )
