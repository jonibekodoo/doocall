"""§9 error taxonomy + uniform envelope for every /api/call/v1 endpoint.

Success:  ``{"success": true, ...endpoint fields...}``
Error:    ``{"success": false, "message": "...", "error_code": "..."}``
(+ endpoint-specific extras, e.g. upload's ``status``/``call_id`` on 409.)
"""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse
from rest_framework import status as http
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ErrorCode:
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"  # 401 (/auth)
    INVALID_API_KEY = "INVALID_API_KEY"  # 401
    DUPLICATE_CALL_ID = "DUPLICATE_CALL_ID"  # 409 (/upload)
    MISSING_FIELD = "MISSING_FIELD"  # 400
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"  # 413
    SUBSCRIPTION_INACTIVE = "SUBSCRIPTION_INACTIVE"  # 402 (new — documented)
    THROTTLED = "THROTTLED"  # 429
    SERVER_ERROR = "SERVER_ERROR"  # 500


class ApiError(Exception):
    """Contract error carrying the §9 envelope + optional extra fields."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}

    def as_response(self) -> Response:
        body: dict[str, Any] = {"success": False, **self.extra}
        body["message"] = self.message
        body["error_code"] = self.error_code
        return Response(body, status=self.status_code)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Map every exception to the §9 envelope."""
    if isinstance(exc, ApiError):
        return exc.as_response()

    if isinstance(exc, ValidationError):
        missing = _flatten_validation_keys(exc.detail)
        return ApiError(
            ErrorCode.MISSING_FIELD,
            f"Missing or invalid field(s): {', '.join(missing) or 'unknown'}",
            http.HTTP_400_BAD_REQUEST,
        ).as_response()

    if isinstance(exc, Throttled):
        wait_s = getattr(exc, "wait", None)
        wait = f" Retry in {int(wait_s)}s." if wait_s else ""
        return ApiError(
            ErrorCode.THROTTLED,
            f"Request was throttled.{wait}",
            http.HTTP_429_TOO_MANY_REQUESTS,
        ).as_response()

    # Fall back to DRF for anything it knows (404, parse errors…), re-enveloped.
    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        return Response(
            {
                "success": False,
                "message": str(detail or "Request failed"),
                "error_code": ErrorCode.SERVER_ERROR
                if response.status_code >= 500
                else ErrorCode.MISSING_FIELD,
            },
            status=response.status_code,
        )
    return None  # unhandled → Django 500 (handler500 below covers DEBUG=False)


def _flatten_validation_keys(detail: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict | list) and not _is_leaf(value):
                keys.extend(_flatten_validation_keys(value, path))
            else:
                keys.append(path)
    elif isinstance(detail, list):
        for item in detail:
            keys.extend(_flatten_validation_keys(item, prefix))
    elif prefix:
        keys.append(prefix)
    return keys


def _is_leaf(value: Any) -> bool:
    if isinstance(value, list):
        return all(not isinstance(v, dict | list) for v in value)
    return False


def server_error(request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
    """Project-wide 500 handler → §9 envelope (used when DEBUG=False)."""
    return JsonResponse(
        {
            "success": False,
            "message": "Unexpected server error",
            "error_code": ErrorCode.SERVER_ERROR,
        },
        status=500,
    )
