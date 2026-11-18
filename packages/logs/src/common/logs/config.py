import logging
import os
import sys
import threading
from logging.config import dictConfig
from typing import Any

import structlog
from opentelemetry import trace
from structlog import get_logger as _get_structlog_logger
from structlog.processors import (
    CallsiteParameter,
    CallsiteParameterAdder,
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    format_exc_info,
)
from structlog.stdlib import BoundLogger, ProcessorFormatter, add_log_level, filter_by_level

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DEPENDENCIES_LOG_LEVEL = "WARNING"

UVICORN_ACCESS_LOGGER_NAME = "uvicorn.access"

SETUP_LOGGING_LOGGER_NAMES: tuple[str | None, ...] = (
    None,
    "uvicorn",
    "uvicorn.error",
    UVICORN_ACCESS_LOGGER_NAME,
    "fastapi",
)

THIRD_PARTY_LOGGER_NAMES: tuple[str, ...] = (
    "apscheduler",
    "urllib3",
    "aiormq",
)

_ACCESS_LOG_PATH_INDEX = 2
HEALTHCHECK_PATH_PREFIX = "/internal/api/health"

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {},
    "handlers": {},
    "loggers": {
        "uvicorn": {"handlers": [], "level": "INFO"},
        "uvicorn.error": {"handlers": [], "level": "INFO"},
        UVICORN_ACCESS_LOGGER_NAME: {"handlers": [], "level": "INFO"},
    },
}


class _HealthcheckAccessLogFilter(logging.Filter):
    """Rebaixa o access log de rotas de healthcheck para DEBUG e descarta fora desse nível.

    Erro no filtro nunca derruba o log (fail-safe): qualquer exceção libera o registro.
    """

    def __init__(self, path_prefix: str, level: int):
        super().__init__()
        self._path_prefix = path_prefix
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return self._should_log(record)
        except Exception:
            return True

    def _should_log(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) <= _ACCESS_LOG_PATH_INDEX:
            return True

        path = str(args[_ACCESS_LOG_PATH_INDEX]).split("?", 1)[0]
        if not path.startswith(self._path_prefix):
            return True

        record.levelno = logging.DEBUG
        record.levelname = logging.getLevelName(logging.DEBUG)
        return self._level <= logging.DEBUG


def add_trace_context(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Inject OpenTelemetry ``trace_id`` / ``span_id`` when the current span is valid."""

    span = trace.get_current_span()
    if not span:
        return event_dict

    span_context = span.get_span_context()
    if not getattr(span_context, "is_valid", False):
        return event_dict

    event_dict.setdefault("trace_id", format(span_context.trace_id, "032x"))
    event_dict.setdefault("span_id", format(span_context.span_id, "016x"))
    return event_dict


def add_thread_id(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Adiciona o identificador da thread atual."""
    event_dict["thread"] = threading.get_ident()
    return event_dict


def extract_from_record(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Extrai file/line de logs que vieram da stdlib."""
    record = event_dict.get("_record")
    if record:
        event_dict["file"] = record.pathname
        event_dict["line"] = record.lineno
    return event_dict


def rename_log_fields(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Renomeia campos para padrão final de saída.

    Não sobrescreve ``file``/``line`` já definidos (ex.: por ``extract_from_record``).
    """
    if "filename" in event_dict:
        event_dict.setdefault("file", event_dict.pop("filename"))
    if "lineno" in event_dict:
        event_dict.setdefault("line", event_dict.pop("lineno"))
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def extract_exception_info(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Captura exc_info automaticamente para nível error."""
    if event_dict.get("level") == "error" and "exception" not in event_dict:
        exc_info = event_dict.get("exc_info")
        if not exc_info and sys.exc_info()[0] is not None:
            event_dict["exc_info"] = True
    return event_dict


def get_shared_processors() -> list[Any]:
    return [
        add_log_level,
        CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.FILENAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.FUNC_NAME,
            ]
        ),
        add_trace_context,
        add_thread_id,
        extract_from_record,
        extract_exception_info,
        format_exc_info,
        rename_log_fields,
        TimeStamper(fmt="iso", utc=True),
        StackInfoRenderer(),
    ]


def _resolve_log_level(settings: Any | None) -> str:
    value = (
        getattr(settings, "logger_level", None)
        or getattr(settings, "log_level", None)
        or os.getenv("LOG_LEVEL")
        or DEFAULT_LOG_LEVEL
    )
    return str(value).upper()


def _resolve_dependencies_log_level(settings: Any | None) -> str:
    value = (
        getattr(settings, "dependencies_logger_level", None)
        or os.getenv("DEPENDENCIES_LOGGER_LEVEL")
        or DEFAULT_DEPENDENCIES_LOG_LEVEL
    )
    return str(value).upper()


def _resolve_environment(settings: Any | None) -> str:
    value = getattr(settings, "environment", None) or os.getenv("ENVIRONMENT") or os.getenv("ENV")
    return str(value or "local").lower()


def _attach(
    handler: logging.Handler, logger_name: str | None = None, level: int = logging.INFO
) -> None:
    """Substitui handlers do logger alvo e pluga handler/formatter."""
    logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def setup_logging(settings: Any | None = None) -> None:
    """Configure structlog with local console and structured JSON elsewhere."""
    log_level = _resolve_log_level(settings)
    environment = _resolve_environment(settings)

    dictConfig(LOGGING_CONFIG)

    shared_processors = get_shared_processors()

    structlog.configure(
        processors=[filter_by_level, *shared_processors, ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    numeric_logger_level = getattr(logging, log_level, logging.INFO)
    renderer = structlog.dev.ConsoleRenderer() if environment == "local" else JSONRenderer()
    formatter = ProcessorFormatter(
        processors=[ProcessorFormatter.remove_processors_meta, *shared_processors, renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    for logger_name in SETUP_LOGGING_LOGGER_NAMES:
        _attach(handler, logger_name, level=numeric_logger_level)

    dependencies_log_level = _resolve_dependencies_log_level(settings)
    numeric_dependencies_level = getattr(logging, dependencies_log_level, logging.WARNING)
    for logger_name in THIRD_PARTY_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(numeric_dependencies_level)

    access_logger = logging.getLogger(UVICORN_ACCESS_LOGGER_NAME)
    access_logger.filters.clear()
    access_logger.addFilter(
        _HealthcheckAccessLogFilter(HEALTHCHECK_PATH_PREFIX, numeric_logger_level)
    )

    _get_structlog_logger(__name__).debug(
        "logging.setup.completed",
        logger_level=log_level,
        environment=environment,
    )


def get_logger(name: str | None = None) -> BoundLogger:
    """Retorna logger structlog."""
    return _get_structlog_logger(name)
