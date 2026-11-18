from http import HTTPStatus
from unittest.mock import patch

import pytest
from common.errors.common_codes import CommonErrorCode
from common.errors.exception_data import ExceptionData
from common.errors.exception_handlers import setup_exception_handlers
from common.errors.exceptions import NotFoundException, UnauthorizedException
from common.errors.renderers.schemas import ErrorSchema
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.testclient import TestClient

SENSITIVE_PASSWORD_MARKER = "senha-vazada-marker"
SENSITIVE_CPF_MARKER = "cpf-vazado-marker"


def _logged_text(call) -> str:
    """Everything a logging sink would receive, as text."""
    return f"{call.args!r}{call.kwargs!r}"


@pytest.fixture
def exception_handler_client():
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/force-unhandled-error")
    async def force_unhandled_error():
        return 1 / 0

    @app.get("/force-not-found")
    async def force_not_found():
        raise NotFoundException(
            exception_data=ExceptionData(
                message="Resource not found",
                detail="The requested resource does not exist",
            )
        )

    @app.get("/force-unauthorized")
    async def force_unauthorized():
        raise UnauthorizedException(
            exception_data=ExceptionData(
                message="Not authorized",
                detail="The request was not authorized",
            )
        )

    @app.get("/force-expected-not-found")
    async def force_expected_not_found():
        raise NotFoundException(
            exception_data=ExceptionData(
                message="Resource not found",
                detail="The requested resource does not exist",
            ),
            is_expected=True,
        )

    @app.get("/force-validation-error")
    async def force_validation_error(required_param: int = Query(...)):
        return {"value": required_param}

    class PayloadSchema(BaseModel):
        name: str

    @app.post("/force-malformed-json")
    async def force_malformed_json(payload: PayloadSchema):
        return payload

    class StrictAgeModel(BaseModel):
        age: int

    @app.get("/force-pydantic-validation-error")
    async def force_pydantic_validation_error():
        StrictAgeModel.model_validate({"age": "not-a-number"})

    class SensitivePayloadSchema(BaseModel):
        senha: str = Field(min_length=32)
        cpf: str = Field(pattern=r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")

    @app.post("/force-sensitive-validation-error")
    async def force_sensitive_validation_error(payload: SensitivePayloadSchema):
        return payload

    @app.get("/force-sensitive-pydantic-validation-error")
    async def force_sensitive_pydantic_validation_error():
        SensitivePayloadSchema.model_validate(
            {"senha": SENSITIVE_PASSWORD_MARKER, "cpf": SENSITIVE_CPF_MARKER}
        )

    class MultiFieldModel(BaseModel):
        name: str
        age: int
        email: str

    @app.get("/force-pydantic-multiple-validation-errors")
    async def force_pydantic_multiple_validation_errors():
        MultiFieldModel.model_validate({"name": 123, "age": "not-a-number", "email": 456})

    @app.get("/force-non-standard-http-error")
    async def force_non_standard_http_error():
        raise StarletteHTTPException(status_code=499, detail="Client Closed Request")

    return TestClient(app, raise_server_exceptions=False)


class TestExceptionHandlers:
    def test_should_log_debug_when_exception_handlers_are_configured(self):
        app = FastAPI()

        with patch("common.errors.exception_handlers.logger.debug") as debug:
            setup_exception_handlers(app)

        debug.assert_any_call("exception_handlers.setup.completed")

    def test_should_return_500_when_unhandled_exception_occurs(self, exception_handler_client):
        response = exception_handler_client.get("/force-unhandled-error")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert error_schema.error_code == CommonErrorCode.UNEXPECTED_ERROR
        assert error_schema.message == "An unexpected internal error occurred"
        assert "Error reference ID:" in error_schema.detail

    def test_should_return_404_when_not_found_exceptions_occurs(self, exception_handler_client):
        response = exception_handler_client.get("/force-not-found")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert error_schema.error_code == HTTPStatus(status.HTTP_404_NOT_FOUND).name
        assert error_schema.message == "Resource not found"
        assert error_schema.detail == "The requested resource does not exist"

    def test_should_log_error_when_application_exception_is_not_expected(
        self, exception_handler_client
    ):
        with patch("common.errors.exception_handlers.logger.error") as error:
            response = exception_handler_client.get("/force-not-found")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        error.assert_called_once()

    def test_should_not_log_error_when_application_exception_is_expected(
        self, exception_handler_client
    ):
        with patch("common.errors.exception_handlers.logger.error") as error:
            response = exception_handler_client.get("/force-expected-not-found")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert error_schema.error_code == HTTPStatus(status.HTTP_404_NOT_FOUND).name
        assert error_schema.message == "Resource not found"
        assert error_schema.detail == "The requested resource does not exist"
        error.assert_not_called()

    def test_should_return_401_when_unauthorized_exceptions_occurs(self, exception_handler_client):
        response = exception_handler_client.get("/force-unauthorized")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert error_schema.error_code == HTTPStatus(status.HTTP_401_UNAUTHORIZED).name
        assert error_schema.message == "Not authorized"
        assert error_schema.detail == "The request was not authorized"

    def test_should_return_422_when_unprocessable_content_occurs(self, exception_handler_client):
        response = exception_handler_client.get("/force-validation-error")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert error_schema.error_code == HTTPStatus(status.HTTP_422_UNPROCESSABLE_CONTENT).name
        assert error_schema.message == "Validation failed for the provided payload"
        assert "Error reference ID:" in error_schema.detail
        assert error_schema.error_messages is not None
        assert len(error_schema.error_messages) == 1
        assert error_schema.error_messages[0]["type"] == "missing"
        assert error_schema.error_messages[0]["loc"] == ["query", "required_param"]
        assert error_schema.error_messages[0]["msg"] == "Field required"
        assert "input" not in error_schema.error_messages[0]
        assert "ctx" not in error_schema.error_messages[0]

    def test_should_return_422_when_malformed_json_occurs(self, exception_handler_client):
        response = exception_handler_client.post(
            "/force-malformed-json",
            content='{ "name": "invalid-syntax ',
            headers={"Content-Type": "application/json"},
        )
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert error_schema.error_code == HTTPStatus(status.HTTP_422_UNPROCESSABLE_CONTENT).name
        assert error_schema.message == "Validation failed for the provided payload"
        assert "Error reference ID:" in error_schema.detail
        assert error_schema.error_messages is not None
        assert len(error_schema.error_messages) == 1
        assert error_schema.error_messages[0]["type"] == "json_invalid"
        assert error_schema.error_messages[0]["loc"] == ["body", 10]
        assert error_schema.error_messages[0]["msg"] == "JSON decode error"
        assert "input" not in error_schema.error_messages[0]
        assert "ctx" not in error_schema.error_messages[0]

    def test_should_handle_starlette_exceptions(self, exception_handler_client):
        with (
            patch("common.errors.exception_handlers.logger.error") as error,
            patch("common.errors.exception_handlers.logger.warning") as warning,
        ):
            response = exception_handler_client.get("/router-not-exists")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert error_schema.error_code == HTTPStatus(status.HTTP_404_NOT_FOUND).name
        assert error_schema.message == "The request is invalid or cannot be served"
        assert "Error reference ID: no-trace-id" in error_schema.detail
        assert error_schema.error_messages is not None
        assert error_schema.error_messages[0]["detail"] == "Not Found"
        error.assert_not_called()
        warning.assert_called_once_with("404: Not Found")

    def test_should_return_422_when_pydantic_validation_error_occurs(
        self, exception_handler_client
    ):
        response = exception_handler_client.get("/force-pydantic-validation-error")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert error_schema.error_code == HTTPStatus(status.HTTP_422_UNPROCESSABLE_CONTENT).name
        assert (
            error_schema.message
            == "The request is invalid or validation failed for the provided payload"
        )
        assert "Error reference ID:" in error_schema.detail
        assert error_schema.error_messages is not None
        assert len(error_schema.error_messages) == 1
        assert "msg" in error_schema.error_messages[0]

    def test_should_return_all_error_messages_when_multiple_pydantic_validation_errors_occur(
        self, exception_handler_client
    ):
        response = exception_handler_client.get("/force-pydantic-multiple-validation-errors")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert error_schema.error_messages is not None
        assert len(error_schema.error_messages) >= 2

        returned_messages = [err["msg"] for err in error_schema.error_messages]
        assert all("msg" in err for err in error_schema.error_messages)
        assert len(returned_messages) == len(error_schema.error_messages)

    def test_should_handle_non_standard_http_status_code(self, exception_handler_client):
        with (
            patch("common.errors.exception_handlers.logger.error") as error,
            patch("common.errors.exception_handlers.logger.warning") as warning,
        ):
            response = exception_handler_client.get("/force-non-standard-http-error")
        error_schema = ErrorSchema(**response.json())

        assert response.status_code == 499
        assert error_schema.error_code == "HTTP_499"
        assert error_schema.message == "The request is invalid or cannot be served"
        assert error_schema.error_messages is not None
        assert error_schema.error_messages[0]["detail"] == "Client Closed Request"
        warning.assert_not_called()
        error.assert_called_once_with("499: Client Closed Request", exc_info=True)


class TestValidationLogsNeverLeakInput:
    """Regressão CYB-001: o log não pode conter o `input` de um erro de validação."""

    def test_should_not_log_input_when_request_validation_fails(self, exception_handler_client):
        with (
            patch("common.errors.exception_handlers.logger.error") as error,
            patch("common.errors.exception_handlers.logger.warning") as warning,
        ):
            response = exception_handler_client.post(
                "/force-sensitive-validation-error",
                json={"senha": SENSITIVE_PASSWORD_MARKER, "cpf": SENSITIVE_CPF_MARKER},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # `error` faria o common-logs anexar o traceback do Pydantic (campo `exception`),
        # que traz o `input` em claro. Ver CYB-001.
        error.assert_not_called()
        warning.assert_called_once()
        assert not warning.call_args.kwargs.get("exc_info")

        logged = _logged_text(warning.call_args)
        assert SENSITIVE_PASSWORD_MARKER not in logged
        assert SENSITIVE_CPF_MARKER not in logged

        logged_errors = warning.call_args.kwargs["errors"]
        assert all("input" not in item and "ctx" not in item for item in logged_errors)
        assert {item["type"] for item in logged_errors} == {
            "string_too_short",
            "string_pattern_mismatch",
        }
        assert all("loc" in item and "msg" in item for item in logged_errors)

        assert SENSITIVE_PASSWORD_MARKER not in response.text
        assert SENSITIVE_CPF_MARKER not in response.text

    def test_should_not_log_input_when_pydantic_validation_error_occurs(
        self, exception_handler_client
    ):
        with (
            patch("common.errors.exception_handlers.logger.error") as error,
            patch("common.errors.exception_handlers.logger.warning") as warning,
        ):
            response = exception_handler_client.get("/force-sensitive-pydantic-validation-error")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        error.assert_not_called()
        warning.assert_called_once()
        assert not warning.call_args.kwargs.get("exc_info")

        logged = _logged_text(warning.call_args)
        assert SENSITIVE_PASSWORD_MARKER not in logged
        assert SENSITIVE_CPF_MARKER not in logged

        logged_errors = warning.call_args.kwargs["errors"]
        assert all("input" not in item and "ctx" not in item for item in logged_errors)
        assert all("type" in item for item in logged_errors)

        assert SENSITIVE_PASSWORD_MARKER not in response.text
        assert SENSITIVE_CPF_MARKER not in response.text
