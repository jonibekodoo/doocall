"""Device authentication for /api/call/v1 (contract §1 + §10).

The app sends ``api_key`` in the JSON body (legacy, always supported).
Per §10 the ``Authorization: Bearer <api_key>`` header is ALSO accepted —
the header wins when both are present.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import status as http
from rest_framework.request import Request

from apps.accounts.models import OperatorProfile
from apps.companies.models import Company
from apps.core import domains

from .errors import ApiError, ErrorCode


def extract_api_key(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ").strip() or None
    data: Any = request.data
    if isinstance(data, dict):
        key = data.get("api_key")
        if isinstance(key, str) and key:
            return key
    return None


def authenticate_device(request: Request) -> OperatorProfile:
    """Resolve the operator from api_key (+ optional user_name cross-check).

    Raises ApiError(INVALID_API_KEY, 401) on failure and
    ApiError(SUBSCRIPTION_INACTIVE, 402) when the company cannot use the API.
    """
    api_key = extract_api_key(request)
    if not api_key:
        raise ApiError(ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED)

    operator: OperatorProfile | None = (
        OperatorProfile.all_objects.select_related("company")
        .filter(api_key=api_key, is_active=True)
        .first()
    )
    if operator is None:
        raise ApiError(ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED)

    # Defence-in-depth: if the body names a different operator, reject.
    data: Any = request.data
    if isinstance(data, dict):
        user_name = data.get("user_name")
        if user_name and user_name != operator.user_name:
            raise ApiError(ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED)

    # Company-subdomain guard: a device posting to <slug>.DOMAIN_ROOT must
    # belong to that company (host is routing, api_key stays the authority).
    sub = domains.company_subdomain(request.get_host())
    if sub is not None and operator.company.slug != sub:
        raise ApiError(ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED)

    require_active_company(operator.company)
    return operator


def require_active_company(company: Company) -> None:
    """402 SUBSCRIPTION_INACTIVE for suspended companies and expired trials."""
    if company.status == Company.Status.SUSPENDED:
        raise ApiError(
            ErrorCode.SUBSCRIPTION_INACTIVE,
            "Company subscription is suspended",
            http.HTTP_402_PAYMENT_REQUIRED,
        )
    if (
        company.status == Company.Status.TRIAL
        and company.trial_ends_at is not None
        and company.trial_ends_at < timezone.now()
    ):
        raise ApiError(
            ErrorCode.SUBSCRIPTION_INACTIVE,
            "Trial period has expired",
            http.HTTP_402_PAYMENT_REQUIRED,
        )
