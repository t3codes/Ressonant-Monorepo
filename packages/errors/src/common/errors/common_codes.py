from enum import StrEnum


class CommonErrorCode(StrEnum):
    """
    Centralizes common/generic error codes shared across all applications.

    Only add error codes here that are reusable by any app in the monorepo.
    Application-specific error codes should be defined within each app under /apps.
    """

    HTTP_INTEGRATION_ERROR = "HTTP_INTEGRATION_ERROR"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_TEMPORARY_UNAVAILABLE = "RESOURCE_TEMPORARY_UNAVAILABLE"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
