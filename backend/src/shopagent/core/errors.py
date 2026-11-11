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

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.hint:
            result["hint"] = self.hint
        if self.details:
            result["details"] = self.details
        return result


class NotFoundError(AppError):
    def __init__(self, message: str, error_code: str = "NOT_FOUND", hint: str | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=404, hint=hint)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Chưa xác thực danh tính", error_code: str = "UNAUTHENTICATED") -> None:
        super().__init__(message, error_code=error_code, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Bạn không có quyền thực hiện thao tác này", error_code: str = "FORBIDDEN") -> None:
        super().__init__(message, error_code=error_code, status_code=403)


class ConflictError(AppError):
    def __init__(self, message: str, error_code: str = "CONFLICT", hint: str | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=409, hint=hint)


class ValidationError(AppError):
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR", hint: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=422, hint=hint, details=details)


class RateLimitError(AppError):
    def __init__(self, message: str = "Đã vượt quá giới hạn tần suất yêu cầu", error_code: str = "RATE_LIMIT_EXCEEDED") -> None:
        super().__init__(message, error_code=error_code, status_code=429, retryable=True, hint="Vui lòng thử lại sau ít phút")


class PolicyViolationError(AppError):
    def __init__(self, message: str, error_code: str = "POLICY_VIOLATION", hint: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, error_code=error_code, status_code=400, hint=hint, details=details)
