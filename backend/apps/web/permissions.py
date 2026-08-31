"""Cabinet view plumbing: JWT auth + tenant scoping + admin gate.

TenantMiddleware can't scope JWT requests (DRF authenticates after middleware
runs), so :class:`CabinetView` activates the tenant context in ``initial()``
— from that point every ``TenantManager`` queryset in the request is
company-scoped, same guarantee as the Phase-2 layer everywhere else.
"""

from __future__ import annotations

from typing import Any, cast

from rest_framework import status as http
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.companies.models import Company
from apps.core import domains
from apps.core.tenancy import set_current_company


class HasCompany(BasePermission):
    message = "user has no company"

    def has_permission(self, request: Request, view: APIView) -> bool:
        return getattr(request.user, "company_id", None) is not None


class IsCompanyAdmin(BasePermission):
    message = "company admin required"

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(getattr(request.user, "is_company_admin", False))


class CabinetView(APIView):
    """Base for every tenant-scoped cabinet endpoint."""

    permission_classes = [IsAuthenticated, HasCompany]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        # Host↔tenant guard: on a company subdomain only that company's
        # users may call the cabinet API (defence-in-depth over JWT scoping).
        sub = domains.company_subdomain(request.get_host())
        user = cast(User, request.user)
        if sub is not None and (user.company is None or user.company.slug != sub):
            raise ApiError(
                ErrorCode.INVALID_API_KEY,
                "wrong company domain",
                http.HTTP_403_FORBIDDEN,
            )
        # After authentication: scope ALL TenantManager querysets to the
        # user's company for the remainder of this request.
        set_current_company(user.company_id)

    @property
    def company(self) -> Company:
        company = cast(User, self.request.user).company
        if company is None:  # pragma: no cover - guarded by HasCompany
            raise ApiError(
                ErrorCode.MISSING_FIELD, "user has no company", http.HTTP_400_BAD_REQUEST
            )
        return company


class AdminCabinetView(CabinetView):
    permission_classes = [IsAuthenticated, HasCompany, IsCompanyAdmin]
