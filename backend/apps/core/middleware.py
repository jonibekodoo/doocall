"""Request-scoped tenant context middleware."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .tenancy import set_current_company


class TenantMiddleware:
    """Bind the authenticated user's company to the tenant context.

    Platform superusers (``company is None``) run unscoped — the Django admin
    relies on that to show all tenants.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        company_id = getattr(user, "company_id", None) if user is not None else None
        set_current_company(company_id)
        try:
            return self.get_response(request)
        finally:
            set_current_company(None)
