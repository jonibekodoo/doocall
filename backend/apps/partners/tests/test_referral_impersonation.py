"""Referral attribution, on-behalf registration, impersonation tokens."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.partners.models import Integrator

from .conftest import client_for

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/web/v1/auth/register"


def register(payload_extra: dict):
    body = {
        "company_name": payload_extra.pop("company_name", "Ref Co"),
        "admin_email": payload_extra.pop("admin_email", "ref@x.uz"),
        "phone": "+998900000000",
        "password": "ref-pass-123",
        **payload_extra,
    }
    return APIClient().post(REGISTER_URL, body, format="json")


class TestReferralAttribution:
    def test_valid_code_binds_company(self, integrator: Integrator) -> None:
        response = register({"ref": integrator.referral_code})
        assert response.status_code == 201
        company = Company.objects.get(slug="ref-co")
        assert company.integrator == integrator
        assert company.acquired_via == Company.AcquiredVia.REFERRAL_LINK

    def test_code_is_case_insensitive(self, integrator: Integrator) -> None:
        response = register(
            {
                "ref": integrator.referral_code.lower(),
                "company_name": "Ref Lower",
                "admin_email": "ref2@x.uz",
            }
        )
        assert response.status_code == 201
        assert Company.objects.get(slug="ref-lower").integrator == integrator

    def test_invalid_code_falls_back_to_self_signup(self, integrator: Integrator) -> None:
        response = register(
            {"ref": "NOPE1234", "company_name": "Fallback Co", "admin_email": "fb@x.uz"}
        )
        assert response.status_code == 201  # registration NEVER blocked
        company = Company.objects.get(slug="fallback-co")
        assert company.integrator is None
        assert company.acquired_via == Company.AcquiredVia.SELF_SIGNUP

    def test_suspended_integrator_code_falls_back(self, integrator: Integrator) -> None:
        integrator.status = Integrator.Status.SUSPENDED
        integrator.save()
        response = register(
            {"ref": integrator.referral_code, "company_name": "Susp Ref", "admin_email": "sr@x.uz"}
        )
        assert response.status_code == 201
        assert Company.objects.get(slug="susp-ref").integrator is None


class TestOnBehalfRegistration:
    def test_manual_registration_binds_and_creates_trial(self, integrator: Integrator) -> None:
        response = client_for(integrator.user).post(
            "/api/partner/v1/companies",
            {
                "company_name": "Client Co",
                "admin_email": "client@x.uz",
                "phone": "+998901112233",
                "password": "client-pass-1",
            },
            format="json",
        )
        assert response.status_code == 201
        company = Company.objects.get(slug="client-co")
        assert company.integrator == integrator
        assert company.acquired_via == Company.AcquiredVia.INTEGRATOR_MANUAL
        assert company.status == Company.Status.TRIAL
        assert company.trial_ends_at is not None
        # The client's admin can log into the cabinet.
        login = APIClient().post(
            "/api/web/v1/auth/login",
            {"email": "client@x.uz", "password": "client-pass-1"},
            format="json",
        )
        assert login.status_code == 200
        assert login.json()["user"]["portal"] == "cabinet"


class TestImpersonation:
    def test_token_is_time_limited_flagged_and_audited(
        self, superadmin: User, bound_company: Company, company_admin: User
    ) -> None:
        response = client_for(superadmin).post(f"/api/admin/v1/impersonate/{bound_company.pk}")
        assert response.status_code == 200
        body = response.json()
        assert body["expires_in_minutes"] == 15

        token = AccessToken(body["access"])
        assert token["impersonated"] is True  # frontend banner flag
        assert token["impersonator_id"] == superadmin.pk
        # ≤ 15 minutes lifetime.
        import time

        assert token["exp"] - time.time() <= 15 * 60 + 5

        # The token really authenticates as the company admin on the cabinet.
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        me = api.get("/api/web/v1/billing/status")
        assert me.status_code in (200, 402)

        assert AuditLog.objects.filter(
            company=bound_company, action="admin.impersonation_started"
        ).exists()

    def test_stop_is_audited(self, superadmin: User) -> None:
        response = client_for(superadmin).post(
            "/api/admin/v1/impersonate/stop", {"company": "bound-co"}, format="json"
        )
        assert response.status_code == 200
        assert AuditLog.objects.filter(action="admin.impersonation_stopped").exists()

    def test_login_response_carries_portal_hint(
        self, superadmin: User, bound_company: Company
    ) -> None:
        superadmin.set_password("root-pass-123")
        superadmin.save()
        response = APIClient().post(
            "/api/web/v1/auth/login",
            {"email": "root@platform.uz", "password": "root-pass-123"},
            format="json",
        )
        assert response.status_code == 200
        user = response.json()["user"]
        assert user["role"] == "superadmin"
        assert user["portal"] == "admin"
