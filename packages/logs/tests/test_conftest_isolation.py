"""Regressão: isolamento de loggers alterados por ``setup_logging``."""

from __future__ import annotations

import logging
from collections.abc import Callable

from common.logs import setup_logging


def test_uvicorn_logger_cleared_after_full_reset(
    full_reset_callable: Callable[[], None],
) -> None:
    setup_logging()
    uvicorn_logger = logging.getLogger("uvicorn")
    assert uvicorn_logger.handlers
    assert uvicorn_logger.propagate is False

    full_reset_callable()

    assert uvicorn_logger.handlers == []
    assert uvicorn_logger.propagate is True


def test_two_setups_do_not_accumulate_uvicorn_handlers(
    full_reset_callable: Callable[[], None],
) -> None:
    setup_logging()
    uvicorn_logger = logging.getLogger("uvicorn")
    assert len(uvicorn_logger.handlers) == 1

    full_reset_callable()
    setup_logging()

    assert len(uvicorn_logger.handlers) == 1


def test_third_party_logger_level_cleared_after_full_reset(
    full_reset_callable: Callable[[], None],
) -> None:
    setup_logging()
    third_party_logger = logging.getLogger("apscheduler")
    assert third_party_logger.level == logging.WARNING

    full_reset_callable()

    assert third_party_logger.level == logging.NOTSET


def test_healthcheck_filter_cleared_after_full_reset(
    full_reset_callable: Callable[[], None],
) -> None:
    setup_logging()
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.filters

    full_reset_callable()

    assert access_logger.filters == []
