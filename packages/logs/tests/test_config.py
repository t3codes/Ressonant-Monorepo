"""Testes de :mod:`common.logs.config`."""

from __future__ import annotations

import json
import logging

import pytest
from common.logs import get_logger, setup_logging
from common.logs.config import (
    THIRD_PARTY_LOGGER_NAMES,
    extract_from_record,
    rename_log_fields,
)


class SettingsStub:
    logger_level = "ERROR"
    environment = "test"


class JsonSettingsStub:
    logger_level = "INFO"
    environment = "test"


class DebugSettingsStub:
    logger_level = "DEBUG"
    environment = "test"


class DependenciesDebugSettingsStub:
    logger_level = "INFO"
    environment = "test"
    dependencies_logger_level = "DEBUG"


def test_setup_logging_configures_root_and_structlog() -> None:
    setup_logging()
    root = logging.getLogger()
    assert root.handlers
    assert root.level == logging.INFO


def test_setup_logging_emits_json_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(JsonSettingsStub())
    get_logger("cfg").warning("json.event")
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["message"] == "json.event"
    assert record["level"] == "warning"


def test_setup_logging_emits_debug_setup_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(DebugSettingsStub())

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert record["message"] == "logging.setup.completed"
    assert record["level"] == "debug"
    assert record["logger_level"] == "DEBUG"
    assert record["environment"] == "test"


def test_setup_logging_respects_logger_level_from_settings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(SettingsStub())
    log = get_logger("cfg")
    log.info("should.not.appear")
    log.error("kept.event")

    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    payloads = [json.loads(line) for line in lines]
    messages = [payload["message"] for payload in payloads]
    assert "should.not.appear" not in messages
    assert "kept.event" in messages


@pytest.mark.parametrize("logger_name", THIRD_PARTY_LOGGER_NAMES)
def test_setup_logging_silences_third_party_loggers_by_default(
    logger_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cobre toda a lista em ``THIRD_PARTY_LOGGER_NAMES`` — um nome novo ali já ganha o teste."""
    setup_logging(JsonSettingsStub())
    logging.getLogger(logger_name).info("noisy.dependency.log")

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("logger_name", THIRD_PARTY_LOGGER_NAMES)
def test_setup_logging_respects_dependencies_logger_level_override(
    logger_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(DependenciesDebugSettingsStub())
    logging.getLogger(logger_name).info("noisy.dependency.log")

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["message"] == "noisy.dependency.log"


def test_extract_from_record_maps_stdlib_record_fields() -> None:
    event_dict = {
        "_record": logging.makeLogRecord({"pathname": "/tmp/file.py", "lineno": 42}),
    }
    mapped = extract_from_record(logging.getLogger("x"), "info", event_dict)
    assert mapped["file"] == "/tmp/file.py"
    assert mapped["line"] == 42


def test_rename_log_fields_maps_event_to_message() -> None:
    payload = {"event": "hello", "filename": "a.py", "lineno": 10}
    mapped = rename_log_fields(logging.getLogger("x"), "info", payload)
    assert mapped["message"] == "hello"
    assert mapped["file"] == "a.py"
    assert mapped["line"] == 10


def test_rename_log_fields_preserves_record_file_line() -> None:
    logger = logging.getLogger("x")
    payload = {
        "_record": logging.makeLogRecord({"pathname": "/app/real_handler.py", "lineno": 99}),
        "filename": "wrapper.py",
        "lineno": 12,
        "event": "stdlib.event",
    }
    payload = extract_from_record(logger, "info", payload)
    mapped = rename_log_fields(logger, "info", payload)
    assert mapped["file"] == "/app/real_handler.py"
    assert mapped["line"] == 99
    assert mapped["message"] == "stdlib.event"
    assert "filename" not in mapped
    assert "lineno" not in mapped


def test_error_log_includes_exception_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(JsonSettingsStub())
    log = get_logger("cfg")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("error.event")

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["message"] == "error.event"
    assert "exception" in record
    assert "ValueError" in record["exception"]
    assert "boom" in record["exception"]
    assert "stack" not in record


def test_stack_info_uses_stack_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(JsonSettingsStub())
    get_logger("cfg").info("stack.event", stack_info=True)

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["message"] == "stack.event"
    assert "stack" in record
    assert record["stack"]
    assert "exception" not in record


def test_setup_logging_uses_console_renderer_for_local(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging()
    get_logger("cfg").warning("local.event")
    assert "local.event" in capsys.readouterr().out
