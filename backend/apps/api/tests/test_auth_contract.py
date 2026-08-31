"""§4 contract tests — literal payload replays."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, SimCard

from .conftest import DOC_API_KEY

pytestmark = pytest.mark.django_db

AUTH_URL = "/api/call/v1/auth"

# §4 "Request — HOZIRGI (kodda bor, LoginRequest)" — replayed literally.
MINIMAL_PAYLOAD = {
    "username": "operator1",
    "password": "••••••••",
    "server": "https://acme.example.com",
}

# §4 "Request — TO'LIQ (SaaS uchun tavsiya)" — replayed literally.
FULL_PAYLOAD = {
    "username": "operator1",
    "password": "••••••••",
    "server": "https://acme.example.com",
    "phone_numbers": [
        {"sim_slot": 0, "number": "+998901234567"},
        {"sim_slot": 1, "number": "+998931234567"},
    ],
    "full_name": "Jonibek Yorqulov",
    "device": {
        "device_id": "a1b2c3d4e5f6...",
        "model": "Redmi Note 12",
        "manufacturer": "Xiaomi",
        "app_version": "1.0",
        "os_version": "13",
    },
}


class TestAuthContract:
    def test_minimal_legacy_payload(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(AUTH_URL, MINIMAL_PAYLOAD, format="json")

        assert response.status_code == 200
        # §4 success body — exactly these keys.
        assert response.json() == {"success": True, "api_key": DOC_API_KEY}

    def test_full_payload_upserts_everything(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        response = client.post(AUTH_URL, FULL_PAYLOAD, format="json")

        assert response.status_code == 200
        assert response.json() == {"success": True, "api_key": DOC_API_KEY}

        operator.refresh_from_db()
        assert operator.full_name == "Jonibek Yorqulov"

        sims = {s.sim_slot: s.number for s in SimCard.all_objects.filter(operator=operator)}
        # slot 0 upserted (fixture had +998998887766), slot 1 created.
        assert sims == {0: "+998901234567", 1: "+998931234567"}

        device = Device.all_objects.get(operator=operator)
        assert device.device_id == "a1b2c3d4e5f6..."
        assert device.manufacturer == "Xiaomi"
        assert device.model == "Redmi Note 12"
        assert device.last_seen_at is not None

    def test_repeat_login_is_idempotent_upsert(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        assert client.post(AUTH_URL, FULL_PAYLOAD, format="json").status_code == 200
        assert client.post(AUTH_URL, FULL_PAYLOAD, format="json").status_code == 200
        assert SimCard.all_objects.filter(operator=operator).count() == 2
        assert Device.all_objects.filter(operator=operator).count() == 1

    def test_bad_credentials_exact_legacy_body(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        response = client.post(AUTH_URL, {**MINIMAL_PAYLOAD, "password": "wrong"}, format="json")

        assert response.status_code == 401
        body = response.json()
        # Legacy §4 401 body fields preserved…
        assert body["success"] is False
        assert body["api_key"] == ""
        # …plus §9 taxonomy.
        assert body["error_code"] == "INVALID_CREDENTIALS"

    def test_unknown_user_401(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(AUTH_URL, {**MINIMAL_PAYLOAD, "username": "ghost"}, format="json")
        assert response.status_code == 401
        assert response.json()["error_code"] == "INVALID_CREDENTIALS"

    def test_missing_password_400(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(AUTH_URL, {"username": "operator1"}, format="json")
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert body["error_code"] == "MISSING_FIELD"
        assert "password" in body["message"]
