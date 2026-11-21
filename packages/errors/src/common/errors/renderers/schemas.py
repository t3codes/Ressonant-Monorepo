from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSchema:
    status_code: int = Field(..., description="The HTTP status code")
    message: str = Field(..., description="A concise, human-readable message explaining the error")
    detail: str | None = Field(
        None, description="A more detailed explanation of the error (if applicable)"
    )
    error_code: str | None = Field(
        None,
        description="A unique internal application error code (e.g., USER_ALREADY_EXISTS)",
    )
    error_messages: list[dict] | None = Field(
        default=None, description="A list of specific field validation errors"
    )
    error_layer: str | None = Field(
        default=None,
        description="Authorization/policy layer that denied the request: management, domain, or null",
    )
    required_capability: str | None = Field(
        default=None,
        description="Capability or policy required to perform the action, when applicable",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Trace/correlation identifier for debugging and observability",
    )
