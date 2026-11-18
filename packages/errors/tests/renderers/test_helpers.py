import pytest
from common.errors.renderers.helpers import build_trace_reference_detail, get_error_code
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

NO_TRACE_DETAIL = "Error reference ID: no-trace-id"


@pytest.fixture
def trace_id(faker):
    return faker.random_int(min=1, max=2**128 - 1)


@pytest.fixture
def span_context(faker, trace_id):
    return SpanContext(
        trace_id=trace_id,
        span_id=faker.random_int(min=1, max=2**64 - 1),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )


class TestGetErrorCode:
    def test_should_return_http_status_name_for_standard_codes(self):
        assert get_error_code(404) == "NOT_FOUND"
        assert get_error_code(500) == "INTERNAL_SERVER_ERROR"
        assert get_error_code(422) == "UNPROCESSABLE_CONTENT"

    def test_should_return_fallback_for_non_standard_codes(self):
        assert get_error_code(499) == "HTTP_499"
        assert get_error_code(525) == "HTTP_525"
        assert get_error_code(999) == "HTTP_999"


class TestBuildTraceReferenceDetail:
    def test_should_return_placeholder_when_there_is_no_active_span(self):
        assert build_trace_reference_detail() == NO_TRACE_DETAIL

    def test_should_use_the_active_span_trace_id_and_go_back_to_the_placeholder_after_it_ends(
        self, span_context, trace_id
    ):
        expected = f"Error reference ID: {format(trace_id, '032x')}"

        with trace.use_span(NonRecordingSpan(span_context), end_on_exit=False):
            assert build_trace_reference_detail() == expected

        assert build_trace_reference_detail() == NO_TRACE_DETAIL
