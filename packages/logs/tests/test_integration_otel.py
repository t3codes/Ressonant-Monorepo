from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from common.logs import get_logger, setup_logging
from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags


class JsonSettingsStub:
    logger_level = "INFO"
    environment = "test"


@pytest.fixture
def active_known_span() -> Iterator[None]:
    """Anexa um NonRecordingSpan com IDs fixos como span atual."""
    span_context = SpanContext(
        trace_id=0xDEADBEEFCAFEBABE0123456789ABCDEF,
        span_id=0x1122334455667788,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    span = NonRecordingSpan(span_context)
    ctx = trace.set_span_in_context(span)
    token = context.attach(ctx)
    try:
        yield
    finally:
        context.detach(token)


def test_active_span_produces_trace_ids_in_json(
    active_known_span: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(JsonSettingsStub())
    get_logger("integration").info("order.created", order_id=7)

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert record["message"] == "order.created"
    assert record["order_id"] == 7
    assert record["trace_id"] == "deadbeefcafebabe0123456789abcdef"
    assert record["span_id"] == "1122334455667788"
