"""Smoke tests garantindo que ``from common.logs import ...`` funciona."""

from __future__ import annotations

import json
import logging

import common.logs
import pytest
from common.logs import (
    get_logger,
    setup_logging,
)

EXPECTED_PUBLIC_API = frozenset(
    {
        "add_trace_context",
        "get_logger",
        "setup_logging",
    }
)


class JsonSettingsStub:
    logger_level = "INFO"
    environment = "test"


def test_public_exports_match_all() -> None:
    assert frozenset(common.logs.__all__) == EXPECTED_PUBLIC_API


def test_public_api_is_importable() -> None:
    assert callable(setup_logging)
    assert callable(get_logger)


def test_setup_then_log_produces_json(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(JsonSettingsStub())
    log = get_logger("smoke")
    log.info("smoke.event", payload=42)

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "esperava ao menos uma linha de log"
    record = json.loads(captured[-1])

    assert record["message"] == "smoke.event"
    assert record["level"] == "info"
    assert record["payload"] == 42
    assert "timestamp" in record


def test_stdlib_logging_goes_through_same_pipeline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(JsonSettingsStub())
    logging.getLogger("smoke.stdlib").warning("stdlib.event")

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "logging stdlib também deve sair como JSON"
    record = json.loads(captured[-1])

    assert record["message"] == "stdlib.event"
    assert record["level"] == "warning"
