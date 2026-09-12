"""Device host guard: login/upload must use the company's own subdomain or
the neutral api.<root> host — never another company's URL or the site/portal
hosts (bug 2026-09: same username in two companies + wrong base URL)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile

from .conftest import DOC_API_KEY, DOC_PASSWORD, DOC_USERNAME

pytestmark = pytest.mark.django_db

AUTH_URL = "/api/call/v1/auth"
UPLOAD_URL = "/api/call/v1/upload"


@pytest.fixture(autouse=True)
def _domains(settings: Any) -> None:
    settings.DOMAIN_ROOT = "doocall.uz"
    settings.DOMAIN_APP = "app.doocall.uz"
    settings.DOMAIN_ADMIN = "app.admin.doocall.uz"
    settings.ALLOWED_HOSTS = ["*"]


def _login(host: str) -> Any:
    return APIClient().post(
        AUTH_URL,
        {"username": DOC_USERNAME, "password": DOC_PASSWORD, "server": ""},
        format="json",
        HTTP_HOST=host,
    )


def _upload(host: str) -> Any:
    return APIClient().post(
        UPLOAD_URL,
        {
            "api_key": DOC_API_KEY,
            "call_id": f"host-{host}",
            "call_type": "inbound",
            "call_status": "answered",
            "from": "+998901112233",
            "to": "+998900000000",
            "counterparty_number": "+998901112233",
            "sim_slot": 0,
            "duration": 5,
            "start_time": "2026-09-12 10:00:00",
            "end_time": "2026-09-12 10:00:05",
            "audio_filename": "none",
        },
        format="json",
        HTTP_HOST=host,
    )


class TestLoginHostGuard:
    def test_own_subdomain_ok(self, operator: OperatorProfile) -> None:
        assert _login("acme.doocall.uz").json()["success"] is True

    def test_neutral_api_host_ok(self, operator: OperatorProfile) -> None:
        assert _login("api.doocall.uz").json()["success"] is True

    def test_wrong_company_subdomain_rejected(self, operator: OperatorProfile) -> None:
        response = _login("other.doocall.uz")
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_CREDENTIALS"

    def test_site_and_portal_hosts_rejected(self, operator: OperatorProfile) -> None:
        for host in ("doocall.uz", "www.doocall.uz", "app.doocall.uz", "app.admin.doocall.uz"):
            assert _login(host).status_code == 401, host


class TestUploadHostGuard:
    def test_own_subdomain_ok(self, operator: OperatorProfile, fake_storage: Any) -> None:
        assert _upload("acme.doocall.uz").status_code == 200

    def test_neutral_api_host_ok(self, operator: OperatorProfile, fake_storage: Any) -> None:
        assert _upload("api.doocall.uz").status_code == 200

    def test_wrong_company_subdomain_rejected(self, operator: OperatorProfile) -> None:
        assert _upload("other.doocall.uz").status_code == 401

    def test_portal_hosts_rejected(self, operator: OperatorProfile) -> None:
        assert _upload("app.doocall.uz").status_code == 401
        assert _upload("doocall.uz").status_code == 401
