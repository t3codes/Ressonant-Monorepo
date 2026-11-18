"""Isolamento de estado global dos testes de ``common.logs``."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
import structlog
from common.logs.config import SETUP_LOGGING_LOGGER_NAMES, THIRD_PARTY_LOGGER_NAMES

_RESET_LOGGER_NAMES: tuple[str | None, ...] = (
    *SETUP_LOGGING_LOGGER_NAMES,
    *THIRD_PARTY_LOGGER_NAMES,
)


@dataclass
class LoggerState:
    handlers: list[logging.Handler]
    level: int
    propagate: bool
    filters: list[logging.Filter]


def snapshot_logger(name: str | None) -> LoggerState:
    logger = logging.getLogger(name)
    return LoggerState(
        handlers=list(logger.handlers),
        level=logger.level,
        propagate=logger.propagate,
        filters=list(logger.filters),
    )


def restore_logger(name: str | None, state: LoggerState) -> None:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    for handler in state.handlers:
        logger.addHandler(handler)
    logger.setLevel(state.level)
    logger.propagate = state.propagate
    logger.filters.clear()
    for log_filter in state.filters:
        logger.addFilter(log_filter)


def reset_logger(name: str | None) -> None:
    logger = logging.getLogger(name)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    for log_filter in logger.filters[:]:
        logger.removeFilter(log_filter)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def full_reset() -> None:
    structlog.reset_defaults()
    for logger_name in _RESET_LOGGER_NAMES:
        reset_logger(logger_name)


@pytest.fixture
def full_reset_callable() -> Callable[[], None]:
    """Expõe ``full_reset`` para testes que precisam resetar loggers no meio do caso."""
    return full_reset


@pytest.fixture(autouse=True)
def _isolate_logs_state() -> Iterator[None]:
    """Reseta estado global da lib antes e depois de cada teste."""
    snapshots = [(logger_name, snapshot_logger(logger_name)) for logger_name in _RESET_LOGGER_NAMES]

    full_reset()
    try:
        yield
    finally:
        full_reset()
        for logger_name, state in snapshots:
            restore_logger(logger_name, state)
