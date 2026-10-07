"""Domain exceptions, translated into HTTP responses by the app's handlers."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing business rule violations."""

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    """The request conflicts with current resource state (duplicate, in-use, ...)."""

    status_code = 409
    code = "conflict"


class ValidationError(DomainError):
    status_code = 422
    code = "unprocessable_entity"
