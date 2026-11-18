from http import HTTPStatus

import pytest
from common.errors.common_codes import CommonErrorCode
from common.errors.exception_data import ExceptionData
from common.errors.exceptions import ApplicationException, NotFoundException
from common.errors.renderers.default import DefaultErrorRenderer
from common.errors.renderers.protocol import ErrorRenderer
from common.errors.renderers.schemas import ErrorSchema
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

NO_TRACE_DETAIL = "Error reference ID: no-trace-id"
NON_STANDARD_STATUS_CODE = 499


@pytest.fixture
def renderer():
    return DefaultErrorRenderer()


class TestRenderApplicationException:
    def test_should_return_the_error_schema_of_the_exception(self, renderer, faker):
        message = faker.sentence()
        detail = faker.sentence()
        error_messages = [{"field": faker.word()}]

        exc = NotFoundException(
            ExceptionData(message=message, detail=detail, error_messages=error_messages)
        )

        status_code, body = renderer.render(exc)

        assert status_code == status.HTTP_404_NOT_FOUND
        assert body == ErrorSchema(
            status_code=status.HTTP_404_NOT_FOUND,
            message=message,
            detail=detail,
            error_code="NOT_FOUND",
            error_messages=error_messages,
        )

    def test_should_keep_the_status_code_and_the_absent_error_code_of_the_base_exception(
        self, renderer, faker
    ):
        exc = ApplicationException(ExceptionData(message=faker.sentence()), HTTPStatus.CONFLICT)

        status_code, body = renderer.render(exc)

        assert status_code == HTTPStatus.CONFLICT
        assert body.status_code == HTTPStatus.CONFLICT
        assert body.error_code is None

    def test_should_not_leak_the_debug_message(self, renderer, faker):
        debug_message = faker.sentence()

        exc = NotFoundException(
            ExceptionData(message=faker.sentence(), debug_message=debug_message)
        )

        _, body = renderer.render(exc)

        assert debug_message not in str(body)


class TestRenderHttp:
    def test_should_wrap_the_detail_into_error_messages(self, renderer, faker):
        detail = faker.sentence()

        exc = StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

        status_code, body = renderer.render_http(exc)

        assert status_code == status.HTTP_404_NOT_FOUND
        assert body.message == "The request is invalid or cannot be served"
        assert body.error_code == "NOT_FOUND"
        assert body.detail == NO_TRACE_DETAIL
        assert body.error_messages == [{"detail": detail}]

    def test_should_omit_error_messages_when_there_is_no_detail(self, renderer):
        exc = StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="")

        _, body = renderer.render_http(exc)

        assert body.error_messages is None

    def test_should_fall_back_to_the_generic_code_for_non_standard_status(self, renderer, faker):
        detail = faker.sentence()

        exc = StarletteHTTPException(status_code=NON_STANDARD_STATUS_CODE, detail=detail)

        status_code, body = renderer.render_http(exc)

        assert status_code == NON_STANDARD_STATUS_CODE
        assert body.error_code == f"HTTP_{NON_STANDARD_STATUS_CODE}"
        assert body.error_messages == [{"detail": detail}]


class TestRenderValidation:
    def test_should_map_the_errors_and_drop_input_and_ctx(self, renderer, faker):
        field = faker.word()
        msg = faker.sentence()

        exc = RequestValidationError(
            errors=[
                {
                    "loc": ("query", field),
                    "msg": msg,
                    "type": "missing",
                    "input": None,
                    "ctx": {faker.word(): faker.word()},
                }
            ]
        )

        status_code, body = renderer.render_validation(exc)

        assert status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert body.message == "Validation failed for the provided payload"
        assert body.error_code == "UNPROCESSABLE_CONTENT"
        assert body.detail == NO_TRACE_DETAIL
        assert len(body.error_messages) == 1

        error_message = body.error_messages[0]
        assert tuple(error_message["loc"]) == ("query", field)
        assert error_message["msg"] == msg
        assert error_message["type"] == "missing"
        assert "input" not in error_message
        assert "ctx" not in error_message

    def test_should_return_one_entry_per_error(self, renderer, faker):
        fields = faker.words(nb=3, unique=True)

        exc = RequestValidationError(
            errors=[
                {"loc": ("body", field), "msg": faker.sentence(), "type": "missing"}
                for field in fields
            ]
        )

        _, body = renderer.render_validation(exc)

        assert len(body.error_messages) == len(fields)


class TestRenderPydanticValidation:
    def test_should_keep_only_the_message_of_each_error(self, renderer, faker):
        class AgeModel(BaseModel):
            age: int

        with pytest.raises(ValidationError) as exc_info:
            AgeModel.model_validate({"age": faker.word()})

        status_code, body = renderer.render_pydantic_validation(exc_info.value)

        assert status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert (
            body.message == "The request is invalid or validation failed for the provided payload"
        )
        assert body.error_code == "UNPROCESSABLE_CONTENT"
        assert body.detail == NO_TRACE_DETAIL
        assert [set(error_message) for error_message in body.error_messages] == [{"msg"}]

    def test_should_return_one_entry_per_error(self, renderer, faker):
        class MultiFieldModel(BaseModel):
            name: str
            age: int

        with pytest.raises(ValidationError) as exc_info:
            MultiFieldModel.model_validate({"name": faker.random_int(), "age": faker.word()})

        _, body = renderer.render_pydantic_validation(exc_info.value)

        assert len(body.error_messages) == 2


class TestRenderUnhandled:
    def test_should_hide_the_original_error(self, renderer, faker):
        original_error = faker.sentence()

        status_code, body = renderer.render_unhandled(ZeroDivisionError(original_error))

        assert status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert body.message == "An unexpected internal error occurred"
        assert body.error_code == CommonErrorCode.UNEXPECTED_ERROR
        assert body.detail == NO_TRACE_DETAIL
        assert original_error not in str(body)


class TestRendererContract:
    @pytest.mark.parametrize(
        "method",
        [
            "render",
            "render_http",
            "render_validation",
            "render_pydantic_validation",
            "render_unhandled",
        ],
    )
    def test_default_renderer_should_implement_every_protocol_method(self, method):
        assert callable(getattr(ErrorRenderer, method, None))
        assert callable(getattr(DefaultErrorRenderer, method, None))

    def test_subclass_should_inherit_the_methods_it_does_not_override(self, faker):
        class OnlyApplicationRenderer(DefaultErrorRenderer):
            def render(self, exc):
                return exc.status_code, {"message": exc.exception_data.message}

        renderer = OnlyApplicationRenderer()
        message = faker.sentence()

        status_code, body = renderer.render(NotFoundException(ExceptionData(message=message)))
        assert status_code == status.HTTP_404_NOT_FOUND
        assert body == {"message": message}

        _, inherited_body = renderer.render_unhandled(ZeroDivisionError())
        assert isinstance(inherited_body, ErrorSchema)
        assert inherited_body.error_code == CommonErrorCode.UNEXPECTED_ERROR
