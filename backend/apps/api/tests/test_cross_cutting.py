"""Cross-cutting behaviour: Bearer auth, 402 SUBSCRIPTION_INACTIVE, throttling."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.companies.models import Company

from .conftest import DOC_API_KEY

pytestmark = pytest.mark.django_db

STATS_URL = "/api/call/v1/stats/summary"
AUTH_URL = "/api/call/v1/auth"


class TestBearerAuth:
    def test_bearer_header_instead_of_body(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        response = client.post(
            STATS_URL,
            {"user_name": "operator1"},  # no api_key in body
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {DOC_API_KEY}",
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_header_wins_over_body(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            STATS_URL,
            {"user_name": "operator1", "api_key": "garbage-in-body"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {DOC_API_KEY}",
        )
        assert response.status_code == 200

    def test_wrong_user_name_with_valid_key_rejected(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        response = client.post(
            STATS_URL,
            {"user_name": "someone-else", "api_key": DOC_API_KEY},
            format="json",
        )
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_API_KEY"

    def test_no_key_at_all_401(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(STATS_URL, {"user_name": "operator1"}, format="json")
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_API_KEY"


class TestSubscriptionInactive:
    def test_suspended_company_402_on_device_endpoints(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        operator.company.status = Company.Status.SUSPENDED
        operator.company.save(update_fields=["status"])

        response = client.post(
            STATS_URL, {"user_name": "operator1", "api_key": DOC_API_KEY}, format="json"
        )
        assert response.status_code == 402
        assert response.json() == {
            "success": False,
            "message": "Company subscription is suspended",
            "error_code": "SUBSCRIPTION_INACTIVE",
        }

    def test_suspended_company_402_on_auth(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        operator.company.status = Company.Status.SUSPENDED
        operator.company.save(update_fields=["status"])

        response = client.post(
            AUTH_URL,
            {"username": "operator1", "password": "••••••••"},
            format="json",
        )
        assert response.status_code == 402
        assert response.json()["error_code"] == "SUBSCRIPTION_INACTIVE"

    def test_expired_trial_402(self, client: APIClient, operator: OperatorProfile) -> None:
        operator.company.status = Company.Status.TRIAL
        operator.company.trial_ends_at = timezone.now() - timedelta(days=1)
        operator.company.save(update_fields=["status", "trial_ends_at"])

        response = client.post(
            STATS_URL, {"user_name": "operator1", "api_key": DOC_API_KEY}, format="json"
        )
        assert response.status_code == 402
        assert response.json()["error_code"] == "SUBSCRIPTION_INACTIVE"

    def test_live_trial_still_allowed(self, client: APIClient, operator: OperatorProfile) -> None:
        operator.company.status = Company.Status.TRIAL
        operator.company.trial_ends_at = timezone.now() + timedelta(days=7)
        operator.company.save(update_fields=["status", "trial_ends_at"])

        response = client.post(
            STATS_URL, {"user_name": "operator1", "api_key": DOC_API_KEY}, format="json"
        )
        assert response.status_code == 200


class TestThrottling:
    def test_throttle_429_with_envelope(
        self,
        client: APIClient,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # DRF binds THROTTLE_RATES at import time — patch the class attribute.
        from rest_framework.throttling import ScopedRateThrottle

        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"stats": "2/min"})

        payload = {"user_name": "operator1", "api_key": DOC_API_KEY}
        assert client.post(STATS_URL, payload, format="json").status_code == 200
        assert client.post(STATS_URL, payload, format="json").status_code == 200
        response = client.post(STATS_URL, payload, format="json")

        assert response.status_code == 429
        body = response.json()
        assert body["success"] is False
        assert body["error_code"] == "THROTTLED"
