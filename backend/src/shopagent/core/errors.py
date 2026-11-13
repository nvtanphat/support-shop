"""Standard error taxonomy and domain exceptions."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        retryable: bool = False,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.retryable = retryable
        self.hint = hint
        self.details = details or {}



class NotFoundError(AppError):
    def __init__(self, message: str, error_code: str = "NOT_FOUND", hint: str | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=404, hint=hint)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Bạn không có quyền thực hiện thao tác này", error_code: str = "FORBIDDEN") -> None:
        super().__init__(message, error_code=error_code, status_code=403)


class ConflictError(AppError):
    def __init__(self, message: str, error_code: str = "CONFLICT", hint: str | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=409, hint=hint)


class ValidationError(AppError):
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR", hint: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=422, hint=hint, details=details)
