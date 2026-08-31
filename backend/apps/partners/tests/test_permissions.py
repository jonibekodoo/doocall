"""Table-driven permission matrix: endpoints × 5 roles (A.1) + isolation."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.companies.models import Company
from apps.partners.models import Integrator

from .conftest import client_for

pytestmark = pytest.mark.django_db

OK = "2xx"
FORBIDDEN = 403

# (method, url, body) — url may reference fixtures via format placeholders.
ADMIN_STAFF_ENDPOINTS = [
    ("get", "/api/admin/v1/dashboard", None),
    ("get", "/api/admin/v1/companies", None),
    ("get", "/api/admin/v1/integrators", None),
    ("get", "/api/admin/v1/audit", None),
]
ADMIN_SUPER_ENDPOINTS = [
    ("get", "/api/admin/v1/settings/cashback", None),
    ("get", "/api/admin/v1/admins", None),
    ("get", "/api/admin/v1/payouts", None),
    ("post", "/api/admin/v1/impersonate/stop", {}),
]
PARTNER_ENDPOINTS = [
    ("get", "/api/partner/v1/dashboard", None),
    ("get", "/api/partner/v1/companies", None),
    ("get", "/api/partner/v1/accruals", None),
    ("get", "/api/partner/v1/payouts", None),
    ("get", "/api/partner/v1/profile", None),
]


def call(client, method: str, url: str, body):
    return getattr(client, method)(url, body, format="json")


def expect(response, expected) -> bool:
    if expected == OK:
        return 200 <= response.status_code < 300
    return response.status_code == expected


class TestPermissionMatrix:
    """Every endpoint group × every role — the A.1 matrix, executable."""

    @pytest.mark.parametrize("method,url,body", ADMIN_STAFF_ENDPOINTS)
    def test_staff_endpoints(
        self,
        method,
        url,
        body,
        superadmin: User,
        platform_admin: User,
        integrator: Integrator,
        company_admin: User,
        company_user: User,
    ) -> None:
        assert expect(call(client_for(superadmin), method, url, body), OK)
        assert expect(call(client_for(platform_admin), method, url, body), OK)
        assert expect(call(client_for(integrator.user), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_admin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_user), method, url, body), FORBIDDEN)
        assert call(client_for(None), method, url, body).status_code in (401, 403)

    @pytest.mark.parametrize("method,url,body", ADMIN_SUPER_ENDPOINTS)
    def test_superadmin_only_endpoints(
        self,
        method,
        url,
        body,
        superadmin: User,
        platform_admin: User,
        integrator: Integrator,
        company_admin: User,
        company_user: User,
    ) -> None:
        assert expect(call(client_for(superadmin), method, url, body), OK)
        # platform_admin explicitly excluded (settings, admins, payouts, imp.)
        assert expect(call(client_for(platform_admin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(integrator.user), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_admin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_user), method, url, body), FORBIDDEN)

    @pytest.mark.parametrize("method,url,body", PARTNER_ENDPOINTS)
    def test_partner_endpoints(
        self,
        method,
        url,
        body,
        superadmin: User,
        platform_admin: User,
        integrator: Integrator,
        company_admin: User,
        company_user: User,
    ) -> None:
        assert expect(call(client_for(integrator.user), method, url, body), OK)
        # Even platform staff do NOT use the partner portal.
        assert expect(call(client_for(superadmin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(platform_admin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_admin), method, url, body), FORBIDDEN)
        assert expect(call(client_for(company_user), method, url, body), FORBIDDEN)

    def test_override_editing_is_superadmin_only(
        self, superadmin: User, platform_admin: User, integrator: Integrator
    ) -> None:
        url = f"/api/admin/v1/integrators/{integrator.pk}"
        body = {"cashback_percent_override": "20.00"}
        assert client_for(platform_admin).patch(url, body, format="json").status_code == 403
        assert client_for(superadmin).patch(url, body, format="json").status_code == 200
        integrator.refresh_from_db()
        assert str(integrator.cashback_percent_override) == "20.00"

    def test_platform_admin_can_edit_other_integrator_fields(
        self, platform_admin: User, integrator: Integrator
    ) -> None:
        url = f"/api/admin/v1/integrators/{integrator.pk}"
        response = client_for(platform_admin).patch(url, {"name": "Renamed"}, format="json")
        assert response.status_code == 200

    def test_suspended_integrator_loses_partner_portal(self, integrator: Integrator) -> None:
        integrator.status = Integrator.Status.SUSPENDED
        integrator.save()
        response = client_for(integrator.user).get("/api/partner/v1/dashboard")
        assert response.status_code == 403


class TestIsolation:
    """Item 6: integrators can never reach operational company data."""

    def test_integrator_blocked_from_cabinet_api(
        self, integrator: Integrator, bound_company: Company
    ) -> None:
        client = client_for(integrator.user)
        for url in [
            "/api/web/v1/calls",
            "/api/web/v1/contacts",
            "/api/web/v1/settings/users",
            "/api/web/v1/settings/devices",
            "/api/web/v1/dashboard",
        ]:
            response = client.get(url)
            assert response.status_code == 403, url  # HasCompany guard

    def test_partner_company_payload_has_no_operational_fields(
        self, integrator: Integrator, bound_company: Company
    ) -> None:
        body = (
            client_for(integrator.user)
            .get(f"/api/partner/v1/companies/{bound_company.pk}")
            .json()["company"]
        )
        leaked = {"calls", "call_records", "contacts", "users", "devices", "operators"}
        assert not (leaked & set(body.keys()))

    def test_integrator_cannot_see_foreign_company(
        self, integrator: Integrator, integrator_override: Integrator
    ) -> None:
        from .conftest import make_company

        foreign = make_company("foreign-co", integrator=integrator_override)
        response = client_for(integrator.user).get(f"/api/partner/v1/companies/{foreign.pk}")
        assert response.status_code == 404

    def test_company_login_routes_to_cabinet_portal(
        self, company_admin: User, superadmin: User, integrator: Integrator
    ) -> None:
        from apps.partners.services import portal_for, role_name

        assert portal_for(role_name(company_admin)) == "cabinet"
        assert portal_for(role_name(superadmin)) == "admin"
        assert portal_for(role_name(integrator.user)) == "partner"
