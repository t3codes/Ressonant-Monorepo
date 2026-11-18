from http import HTTPStatus

from opentelemetry import trace


def build_trace_reference_detail() -> str:
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    trace_reference_id = (
        format(span_context.trace_id, "032x") if span_context.is_valid else "no-trace-id"
    )
    return f"Error reference ID: {trace_reference_id}"


def get_error_code(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).name
    except ValueError:
        return f"HTTP_{status_code}"
