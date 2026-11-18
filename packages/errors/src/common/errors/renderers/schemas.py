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
