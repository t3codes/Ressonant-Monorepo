from http import HTTPStatus

import pytest
from common.errors.common_codes import CommonErrorCode
from common.errors.exception_data import ExceptionData
from common.errors.exceptions import (
    ApplicationException,
    BadRequestException,
    ForbiddenException,
    HttpIntegrationException,
    NotFoundException,
    UnauthorizedException,
    UnexpectedException,
)
from fastapi import status


class TestApplicationExceptions:
    ERROR_DETAIL = "some_error_detail"
    ERROR_MESSAGE = "some_error_message"
    ERROR_CODE = "XPTO_1234_ERROR_CODE"
    DEBUG_MESSAGE = "some_debug_message"
    ORIGINAL_ERROR = [
        {
            "loc": ("header", "x-api-key"),
            "msg": "invalid uuid format",
            "type": "value_error.uuid",
            "input": "not-a-uuid-string",
        }
    ]
    ERROR_MESSAGES = [{"message_title": "Resource not found", "message_content": "try again"}]

    @pytest.mark.parametrize("invalid_status_code", [200, 201, 204, 301, 302, 399])
    def test_application_exception_rejects_non_error_status_codes(self, invalid_status_code):
        with pytest.raises(ValueError, match="must be a client .4xx. or server .5xx. error code"):
            ApplicationException(
                ExceptionData(
                    message=self.ERROR_MESSAGE,
                    detail=self.ERROR_DETAIL,
                ),
                status_code=invalid_status_code,
            )

    def test_application_exception_str_returns_message(self):
        exc = ApplicationException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
            ),
            status_code=HTTPStatus.CONFLICT,
        )

        assert str(exc) == self.ERROR_MESSAGE
        assert exc.args == (self.ERROR_MESSAGE,)

    def test_application_exception_to_dict(self):
        exc = ApplicationException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                error_code=self.ERROR_CODE,
                debug_message=self.DEBUG_MESSAGE,
                original_errors=self.ORIGINAL_ERROR,
                error_messages=self.ERROR_MESSAGES,
            ),
            status_code=HTTPStatus.CONFLICT,
        )

        data = exc.to_dict()

        assert exc.status_code == HTTPStatus.CONFLICT
        assert data["message"] == self.ERROR_MESSAGE
        assert data["detail"] == self.ERROR_DETAIL
        assert data["error_code"] == self.ERROR_CODE
        assert data["debug_message"] == self.DEBUG_MESSAGE
        assert data["original_errors"] == self.ORIGINAL_ERROR
        assert data["error_messages"] == self.ERROR_MESSAGES

    @pytest.mark.parametrize(
        "provided_code, expected_code, debug_message",
        [
            (None, "BAD_REQUEST", ""),
            (ERROR_CODE, ERROR_CODE, DEBUG_MESSAGE),
        ],
    )
    def test_bad_request_exception(self, provided_code, expected_code, debug_message):
        exc = BadRequestException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                debug_message=debug_message,
                error_code=provided_code,
            )
        )

        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.error_code == expected_code
        assert exc.exception_data.debug_message == debug_message

    @pytest.mark.parametrize(
        "provided_code, expected_code, debug_msg",
        [
            (None, "UNAUTHORIZED", DEBUG_MESSAGE),
            (ERROR_CODE, ERROR_CODE, ""),
        ],
    )
    def test_unauthorized_exception(self, provided_code, expected_code, debug_msg):
        exc = UnauthorizedException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                error_code=provided_code,
                debug_message=debug_msg,
            )
        )

        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.exception_data.message == self.ERROR_MESSAGE
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.error_code == expected_code
        assert exc.exception_data.debug_message == debug_msg

    @pytest.mark.parametrize(
        "provided_code, expected_code, debug_msg",
        [
            (None, "FORBIDDEN", DEBUG_MESSAGE),
            (ERROR_CODE, ERROR_CODE, ""),
        ],
    )
    def test_forbidden_exception(self, provided_code, expected_code, debug_msg):
        exc = ForbiddenException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                error_code=provided_code,
                debug_message=debug_msg,
            )
        )

        assert exc.status_code == status.HTTP_403_FORBIDDEN
        assert exc.exception_data.message == self.ERROR_MESSAGE
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.error_code == expected_code
        assert exc.exception_data.debug_message == debug_msg

    @pytest.mark.parametrize(
        "provided_code, expected_code, debug_msg",
        [
            (None, "NOT_FOUND", DEBUG_MESSAGE),
            (ERROR_CODE, ERROR_CODE, ""),
        ],
    )
    def test_not_found_exception(self, provided_code, expected_code, debug_msg):
        exc = NotFoundException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                error_code=provided_code,
                debug_message=debug_msg,
            )
        )

        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.message == self.ERROR_MESSAGE
        assert exc.exception_data.error_code == expected_code
        assert exc.exception_data.debug_message == debug_msg

    @pytest.mark.parametrize(
        "provided_code, expected_code, debug_msg",
        [
            (None, "INTERNAL_SERVER_ERROR", DEBUG_MESSAGE),
            (ERROR_CODE, ERROR_CODE, ""),
        ],
    )
    def test_unexpected_exception(self, provided_code, expected_code, debug_msg):
        exc = UnexpectedException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                error_code=provided_code,
                debug_message=debug_msg,
            )
        )

        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.exception_data.message == self.ERROR_MESSAGE
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.error_code == expected_code
        assert exc.exception_data.debug_message == debug_msg

    @pytest.mark.parametrize(
        "status_in, debug_msg",
        [
            (status.HTTP_502_BAD_GATEWAY, DEBUG_MESSAGE),
            (status.HTTP_503_SERVICE_UNAVAILABLE, ""),
            (status.HTTP_504_GATEWAY_TIMEOUT, "Upstream timeout"),
        ],
    )
    def test_http_integration_exception(self, status_in, debug_msg):
        exc = HttpIntegrationException(
            ExceptionData(
                message=self.ERROR_MESSAGE,
                detail=self.ERROR_DETAIL,
                debug_message=debug_msg,
            ),
            status_code=status_in,
        )

        assert exc.status_code == status_in
        assert exc.exception_data.message == self.ERROR_MESSAGE
        assert exc.exception_data.detail == self.ERROR_DETAIL
        assert exc.exception_data.error_code == CommonErrorCode.HTTP_INTEGRATION_ERROR
        assert exc.exception_data.debug_message == debug_msg

    def test_http_integration_exception_falls_back_to_500_without_a_status_code(self):
        exc = HttpIntegrationException(
            ExceptionData(message=self.ERROR_MESSAGE, detail=self.ERROR_DETAIL),
            status_code=None,
        )

        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.exception_data.error_code == CommonErrorCode.HTTP_INTEGRATION_ERROR
