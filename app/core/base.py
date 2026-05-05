"""Transport-agnostic error type and CIMA call wrapper for core handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.helpers import safe_cima_call


class OperationError(Exception):
    """Domain error raised by any ``core_<op>``.

    Adapters translate it to their native shape:
    - HTTP routes raise ``HTTPException(status_code=err.status_code, detail=err.to_dict())``.
    - Stdio tools return the dict ``err.to_dict()`` so the LLM receives an
      actionable payload instead of an opaque exception.
    """

    def __init__(
        self,
        status_code: int,
        error: str,
        *,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details or {}
        super().__init__(message or error)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.error, "status_code": self.status_code}
        if self.message:
            payload["message"] = self.message
        if self.details:
            payload["details"] = self.details
        return payload


async def safe_call(func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Call CIMA via ``safe_cima_call`` and translate ``HTTPException`` to ``OperationError``.

    ``safe_cima_call`` already maps upstream failures (404/400/502/503/500) to
    ``HTTPException`` — we re-raise as ``OperationError`` so the core stays
    free of FastAPI types from the caller's perspective.
    """
    try:
        return await safe_cima_call(func, *args, **kwargs)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            error = detail.get("error", "upstream_error")
            message = detail.get("message")
            details = {k: v for k, v in detail.items() if k not in {"error", "message"}}
        else:
            error = "upstream_error"
            message = str(detail) if detail else None
            details = None
        raise OperationError(
            exc.status_code,
            error=error,
            message=message,
            details=details,
        ) from exc
