"""Role guards for the admin (/api/admin/v1) and partner (/api/partner/v1)
portals. Matrix (A.1): superadmin ⊃ platform_admin; integrators get ONLY the
partner portal; company users get 403 on both.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import ROLE_INTEGRATOR, ROLE_PLATFORM_ADMIN, ROLE_SUPERADMIN
from .services import role_name


class IsPlatformStaff(BasePermission):
    """superadmin OR platform_admin."""

    message = "platform staff role required"

    def has_permission(self, request: Request, view: APIView) -> bool:
        return role_name(request.user) in (ROLE_SUPERADMIN, ROLE_PLATFORM_ADMIN)


class IsSuperadmin(BasePermission):
    message = "superadmin role required"

    def has_permission(self, request: Request, view: APIView) -> bool:
        return role_name(request.user) == ROLE_SUPERADMIN


class IsIntegrator(BasePermission):
    message = "integrator role required"

    def has_permission(self, request: Request, view: APIView) -> bool:
        if role_name(request.user) != ROLE_INTEGRATOR:
            return False
        profile = getattr(request.user, "integrator_profile", None)
        return profile is not None and profile.status == "active"
