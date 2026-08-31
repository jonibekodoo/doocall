"""Web auth flow: registration funnel, JWT login/refresh-rotation/logout,
password reset via mailhog, email-verification feature flag."""

from __future__ import annotations

from typing import Any

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Subscription
from apps.companies.models import Company
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/web/v1/auth/register"
LOGIN_URL = "/api/web/v1/auth/login"
REFRESH_URL = "/api/web/v1/auth/refresh"
LOGOUT_URL = "/api/web/v1/auth/logout"
RESET_URL = "/api/web/v1/auth/password-reset"
RESET_CONFIRM_URL = "/api/web/v1/auth/password-reset/confirm"
VERIFY_URL = "/api/web/v1/auth/verify-email"
STATUS_URL = "/api/web/v1/billing/status"

COOKIE = "doocall_refresh"

REGISTER_PAYLOAD = {
    "company_name": "Yangi Uy MChJ",
    "admin_email": "boss@yangi-uy.uz",
    "phone": "+998901234567",
    "password": "sup3r-secret",
}


@pytest.fixture(autouse=True)
def _email_backend(settings: Any, db: Any) -> None:
    # PricingSetting comes from the shared conftest `_pricing` fixture.
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


def register(client: APIClient, **overrides: Any) -> Any:
    return client.post(REGISTER_URL, {**REGISTER_PAYLOAD, **overrides}, format="json")


class TestRegistration:
    def test_creates_trial_company_and_admin(self, client: APIClient = None) -> None:  # type: ignore[assignment]
        client = APIClient()
        response = register(client)

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["company"] == {"name": "Yangi Uy MChJ", "slug": "yangi-uy-mchj"}
        assert body["email_verification_required"] is False

        company = Company.objects.get(slug="yangi-uy-mchj")
        assert company.status == Company.Status.TRIAL
        assert company.trial_ends_at is not None

        user = User.objects.get(username="boss@yangi-uy.uz")
        assert user.company_id == company.pk
        assert user.check_password("sup3r-secret")

        subscription = Subscription.all_objects.get(company=company)
        assert subscription.status == Subscription.Status.TRIAL
        assert AuditLog.objects.filter(company=company, action="web.register").exists()

    def test_duplicate_email_400(self) -> None:
        client = APIClient()
        register(client)
        response = register(client, company_name="Other Co")
        assert response.status_code == 400
        assert "email" in response.json()["message"]

    def test_duplicate_company_name_400(self) -> None:
        client = APIClient()
        register(client)
        response = register(client, admin_email="other@x.uz")
        assert response.status_code == 400
        assert "company" in response.json()["message"]

    def test_trial_days_come_from_pricing(self) -> None:
        client = APIClient()
        register(client)
        company = Company.objects.get(slug="yangi-uy-mchj")
        subscription = Subscription.all_objects.get(company=company)
        delta = company.trial_ends_at - subscription.created_at
        assert 13 <= delta.days <= 14  # PricingSetting.trial_days == 14


class TestJwtFlow:
    def login(self, client: APIClient) -> Any:
        return client.post(
            LOGIN_URL,
            {"email": REGISTER_PAYLOAD["admin_email"], "password": REGISTER_PAYLOAD["password"]},
            format="json",
        )

    def test_login_sets_httponly_refresh_cookie(self) -> None:
        client = APIClient()
        register(client)
        response = self.login(client)

        assert response.status_code == 200
        assert response.json()["access"]
        cookie = response.cookies[COOKIE]
        assert cookie["httponly"]
        assert cookie["path"] == "/api/web/v1/auth"
        assert AuditLog.objects.filter(action="web.login").exists()

    def test_access_token_reaches_protected_endpoint(self) -> None:
        client = APIClient()
        register(client)
        access = self.login(client).json()["access"]

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = client.get(STATUS_URL)
        assert response.status_code == 200
        assert response.json()["company"] == "yangi-uy-mchj"

    def test_refresh_rotates_and_blacklists_old(self) -> None:
        client = APIClient()
        register(client)
        old_refresh = self.login(client).cookies[COOKIE].value

        r1 = client.post(REFRESH_URL)  # cookie jar carries the refresh cookie
        assert r1.status_code == 200
        new_refresh = r1.cookies[COOKIE].value
        assert new_refresh != old_refresh

        # Replaying the OLD (blacklisted) token must fail.
        client.cookies[COOKIE] = old_refresh
        r2 = client.post(REFRESH_URL)
        assert r2.status_code == 401

        # The NEW one still works.
        client.cookies[COOKIE] = new_refresh
        assert client.post(REFRESH_URL).status_code == 200

    def test_logout_blacklists_and_clears_cookie(self) -> None:
        client = APIClient()
        register(client)
        refresh = self.login(client).cookies[COOKIE].value

        response = client.post(LOGOUT_URL)
        assert response.status_code == 200
        assert response.cookies[COOKIE].value == ""  # cleared

        client.cookies[COOKIE] = refresh
        assert client.post(REFRESH_URL).status_code == 401  # blacklisted

    def test_bad_password_401(self) -> None:
        client = APIClient()
        register(client)
        response = client.post(
            LOGIN_URL,
            {"email": REGISTER_PAYLOAD["admin_email"], "password": "nope"},
            format="json",
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_CREDENTIALS"

    def test_refresh_without_cookie_401(self) -> None:
        assert APIClient().post(REFRESH_URL).status_code == 401


class TestPasswordReset:
    def test_reset_email_flow(self) -> None:
        client = APIClient()
        register(client)

        assert (
            client.post(
                RESET_URL, {"email": REGISTER_PAYLOAD["admin_email"]}, format="json"
            ).status_code
            == 200
        )
        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].strip()

        response = client.post(
            RESET_CONFIRM_URL,
            {"uid": uid, "token": token, "new_password": "brand-new-pass1"},
            format="json",
        )
        assert response.status_code == 200
        user = User.objects.get(username=REGISTER_PAYLOAD["admin_email"])
        assert user.check_password("brand-new-pass1")

    def test_unknown_email_no_enumeration(self) -> None:
        response = APIClient().post(RESET_URL, {"email": "ghost@x.uz"}, format="json")
        assert response.status_code == 200  # identical response
        assert len(mail.outbox) == 0

    def test_bad_token_400(self) -> None:
        client = APIClient()
        register(client)
        response = client.post(
            RESET_CONFIRM_URL,
            {"uid": "xxx", "token": "yyy", "new_password": "whatever123"},
            format="json",
        )
        assert response.status_code == 400


class TestEmailVerificationFlag:
    def test_flag_off_no_email_login_allowed(self) -> None:
        client = APIClient()
        register(client)
        assert len(mail.outbox) == 0

    def test_flag_on_blocks_login_until_verified(self, settings: Any) -> None:
        settings.EMAIL_VERIFICATION_ENABLED = True
        client = APIClient()
        response = register(client)
        assert response.json()["email_verification_required"] is True
        assert len(mail.outbox) == 1

        login = client.post(
            LOGIN_URL,
            {"email": REGISTER_PAYLOAD["admin_email"], "password": REGISTER_PAYLOAD["password"]},
            format="json",
        )
        assert login.status_code == 403
        assert login.json()["error_code"] == "EMAIL_NOT_VERIFIED"

        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].strip()
        assert (
            client.post(VERIFY_URL, {"uid": uid, "token": token}, format="json").status_code == 200
        )

        assert (
            client.post(
                LOGIN_URL,
                {
                    "email": REGISTER_PAYLOAD["admin_email"],
                    "password": REGISTER_PAYLOAD["password"],
                },
                format="json",
            ).status_code
            == 200
        )


class TestPaywall:
    def test_suspended_company_402_with_paywall_payload(self) -> None:
        client = APIClient()
        register(client)
        access = client.post(
            LOGIN_URL,
            {"email": REGISTER_PAYLOAD["admin_email"], "password": REGISTER_PAYLOAD["password"]},
            format="json",
        ).json()["access"]

        company = Company.objects.get(slug="yangi-uy-mchj")
        company.status = Company.Status.SUSPENDED
        company.save(update_fields=["status"])

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = client.get(STATUS_URL)

        assert response.status_code == 402
        body = response.json()
        assert body["error_code"] == "SUBSCRIPTION_INACTIVE"
        paywall = body["paywall"]
        assert paywall["reason"] == "suspended"
        assert set(paywall.keys()) == {
            "reason",
            "seats",
            "price_per_operator_uzs",
            "amount_due_uzs",
            "providers",
        }
        assert paywall["providers"] == ["payme", "click", "manual"]
