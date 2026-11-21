from pydantic.dataclasses import dataclass


@dataclass
class ExceptionData:
    message: str
    detail: str | None = None
    error_code: str | None = None
    debug_message: str | None = None
    original_errors: list[dict] | None = None
    error_messages: list[dict] | None = None
    error_layer: str | None = None  # "management" | "domain" | None
    required_capability: str | None = None
    correlation_id: str | None = None
