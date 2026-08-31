"""Company-subdomain tenancy: host parsing, guards, landing companies menu."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.companies.models import Company
from apps.core import domains

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _domains(settings: Any) -> None:
    settings.DOMAIN_ROOT = "localhost"
    settings.DOMAIN_APP = "app.localhost"
    settings.DOMAIN_ADMIN = "app.admin.localhost"
    settings.URL_SCHEME = "http"
    settings.ALLOWED_HOSTS = ["*"]


@pytest.fixture
def cab_user(company: Company) -> User:
    return User.objects.create_user(
        username="subadmin@cabinet-co.uz",
        email="subadmin@cabinet-co.uz",
        password="cabinet-sub-1",
        company=company,
        is_company_admin=True,
    )


def _login(client: APIClient, email: str, password: str, **extra: Any) -> Any:
    return client.post(
        "/api/web/v1/auth/login",
        {"email": email, "password": password},
        format="json",
        **extra,
    )


class TestSubdomainParsing:
    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("cabinet-co.localhost", "cabinet-co"),
            ("cabinet-co.localhost:80", "cabinet-co"),
            ("localhost", None),  # bare root
            ("app.localhost", None),  # cabinet/app host
            ("app.admin.localhost", None),  # django admin host
            ("www.localhost", None),  # reserved
            ("a.b.localhost", None),  # nested
            ("testserver", None),  # test client
            ("evil.example.com", None),  # foreign domain
        ],
    )
    def test_company_subdomain(self, host: str, expected: str | None) -> None:
        assert domains.company_subdomain(host) == expected

    def test_urls(self) -> None:
        assert domains.cabinet_url("acme") == "http://acme.localhost/cabinet"
        assert domains.portal_url("partner") == "http://app.localhost/partner"


class TestAuthSubdomainPayload:
    def test_login_returns_cabinet_url_and_domain_cookie(
        self, cab_user: User, settings: Any
    ) -> None:
        settings.REFRESH_COOKIE_DOMAIN = ".localhost"
        response = _login(
            APIClient(), "subadmin@cabinet-co.uz", "cabinet-sub-1", HTTP_HOST="localhost"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["cabinet_url"] == "http://cabinet-co.localhost/cabinet"
        cookie = response.cookies["doocall_refresh"]
        assert cookie["domain"] == ".localhost"

    def test_companies_menu_for_cabinet_user(self, cab_user: User) -> None:
        client = APIClient()
        token = _login(client, "subadmin@cabinet-co.uz", "cabinet-sub-1").json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        body = client.get("/api/web/v1/auth/companies", HTTP_HOST="localhost").json()
        assert body["portal"] == "cabinet"
        assert body["companies"] == [
            {
                "name": "Cabinet Co",
                "slug": "cabinet-co",
                "url": "http://cabinet-co.localhost/cabinet",
            }
        ]
        assert body["portal_url"] == "http://cabinet-co.localhost/cabinet"

    def test_companies_menu_requires_auth(self) -> None:
        assert APIClient().get("/api/web/v1/auth/companies").status_code == 401


class TestCabinetHostGuard:
    def test_own_subdomain_ok_wrong_subdomain_403(self, cab_user: User) -> None:
        client = APIClient()
        token = _login(client, "subadmin@cabinet-co.uz", "cabinet-sub-1").json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        ok = client.get("/api/web/v1/dashboard", HTTP_HOST="cabinet-co.localhost")
        assert ok.status_code == 200

        wrong = client.get("/api/web/v1/dashboard", HTTP_HOST="other-co.localhost")
        assert wrong.status_code == 403

        # Neutral hosts (app domain, test client) keep working.
        assert client.get("/api/web/v1/dashboard", HTTP_HOST="app.localhost").status_code == 200
        assert client.get("/api/web/v1/dashboard").status_code == 200


class TestMobileHostGuard:
    @pytest.fixture
    def operator(self, company: Company) -> OperatorProfile:
        user = User.objects.create_user(username="op-sub@cabinet-co", company=company)
        return OperatorProfile.all_objects.create(
            company=company, user=user, user_name="op-sub", api_key="sub-key-123"
        )

    def test_matching_subdomain_ok(self, operator: OperatorProfile) -> None:
        response = APIClient().post(
            "/api/call/v1/calls/list",
            {"api_key": "sub-key-123", "call_ids": []},
            format="json",
            HTTP_HOST="cabinet-co.localhost",
        )
        assert response.status_code == 200

    def test_wrong_subdomain_rejected(self, operator: OperatorProfile) -> None:
        response = APIClient().post(
            "/api/call/v1/calls/list",
            {"api_key": "sub-key-123", "call_ids": []},
            format="json",
            HTTP_HOST="other-co.localhost",
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_API_KEY"

    def test_neutral_host_still_ok(self, operator: OperatorProfile) -> None:
        response = APIClient().post(
            "/api/call/v1/calls/list",
            {"api_key": "sub-key-123", "call_ids": []},
            format="json",
        )
        assert response.status_code == 200


class TestLoginHostGuard:
    """A subdomain accepts ONLY its own company's logins/sessions."""

    def test_login_on_own_subdomain_ok(self, cab_user: User) -> None:
        response = _login(
            APIClient(),
            "subadmin@cabinet-co.uz",
            "cabinet-sub-1",
            HTTP_HOST="cabinet-co.localhost",
        )
        assert response.status_code == 200

    def test_login_on_foreign_subdomain_rejected(self, cab_user: User) -> None:
        response = _login(
            APIClient(),
            "subadmin@cabinet-co.uz",
            "cabinet-sub-1",
            HTTP_HOST="other-co.localhost",
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_CREDENTIALS"
        # No session material leaks on a failed cross-domain login.
        assert "doocall_refresh" not in response.cookies

    def test_companyless_staff_cannot_login_on_subdomain(self, db: Any) -> None:
        from apps.partners import services
        from apps.partners.models import ROLE_SUPERADMIN

        User.objects.create_user(
            username="root@sub.uz",
            email="root@sub.uz",
            password="root-pass-12",
            role=services.get_platform_role(ROLE_SUPERADMIN),
        )
        response = _login(
            APIClient(), "root@sub.uz", "root-pass-12", HTTP_HOST="cabinet-co.localhost"
        )
        assert response.status_code == 401

    def test_refresh_on_foreign_subdomain_rejected_without_rotation(self, cab_user: User) -> None:
        client = APIClient()
        login = _login(client, "subadmin@cabinet-co.uz", "cabinet-sub-1")
        assert login.status_code == 200

        # Foreign subdomain: refused…
        wrong = client.post("/api/web/v1/auth/refresh", HTTP_HOST="other-co.localhost")
        assert wrong.status_code == 401

        # …and the cookie was NOT burned — own subdomain still refreshes.
        ok = client.post("/api/web/v1/auth/refresh", HTTP_HOST="cabinet-co.localhost")
        assert ok.status_code == 200
        assert ok.json()["user"]["company"] == "cabinet-co"


class TestHandoff:
    """One-time landing → subdomain sign-in code."""

    def _mint(self, cab_user: User) -> tuple[APIClient, str]:
        client = APIClient()
        token = _login(client, "subadmin@cabinet-co.uz", "cabinet-sub-1").json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        code = client.post("/api/web/v1/auth/handoff").json()["code"]
        return client, code

    def test_redeem_on_own_subdomain(self, cab_user: User) -> None:
        _, code = self._mint(cab_user)
        fresh = APIClient()
        response = fresh.post(
            "/api/web/v1/auth/handoff/redeem",
            {"code": code},
            format="json",
            HTTP_HOST="cabinet-co.localhost",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["company"] == "cabinet-co"
        assert "doocall_refresh" in response.cookies

        # single use
        again = fresh.post(
            "/api/web/v1/auth/handoff/redeem",
            {"code": code},
            format="json",
            HTTP_HOST="cabinet-co.localhost",
        )
        assert again.status_code == 401

    def test_redeem_on_foreign_subdomain_rejected(self, cab_user: User) -> None:
        _, code = self._mint(cab_user)
        response = APIClient().post(
            "/api/web/v1/auth/handoff/redeem",
            {"code": code},
            format="json",
            HTTP_HOST="other-co.localhost",
        )
        assert response.status_code == 401

    def test_redeem_garbage_rejected(self, db: Any) -> None:
        response = APIClient().post(
            "/api/web/v1/auth/handoff/redeem", {"code": "nope"}, format="json"
        )
        assert response.status_code == 401

    def test_mint_requires_auth(self, db: Any) -> None:
        assert APIClient().post("/api/web/v1/auth/handoff").status_code == 401


class TestOffDomainUrls:
    """Public tunnels (no wildcard subdomains) get same-host cabinet links."""

    def test_companies_menu_on_foreign_host(self, cab_user: User) -> None:
        client = APIClient()
        token = _login(client, "subadmin@cabinet-co.uz", "cabinet-sub-1").json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        body = client.get(
            "/api/web/v1/auth/companies",
            HTTP_HOST="doocall.jprq.live",
            HTTP_X_FORWARDED_PROTO="https",
        ).json()
        assert body["companies"][0]["url"] == "https://doocall.jprq.live/cabinet"
        assert body["portal_url"] == "https://doocall.jprq.live/cabinet"

    def test_login_cabinet_url_follows_request_host(self, cab_user: User) -> None:
        body = _login(
            APIClient(),
            "subadmin@cabinet-co.uz",
            "cabinet-sub-1",
            HTTP_HOST="doocall.jprq.live",
            HTTP_X_FORWARDED_PROTO="https",
        ).json()
        assert body["user"]["cabinet_url"] == "https://doocall.jprq.live/cabinet"

    def test_product_host_still_gets_subdomain(self, cab_user: User) -> None:
        body = _login(
            APIClient(), "subadmin@cabinet-co.uz", "cabinet-sub-1", HTTP_HOST="localhost"
        ).json()
        assert body["user"]["cabinet_url"] == "http://cabinet-co.localhost/cabinet"
