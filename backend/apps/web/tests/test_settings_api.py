"""Settings APIs: groups, users→seats, devices, toggles, api-key, webhook, license."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, SimCard
from apps.companies.models import Company
from apps.web import tasks as web_tasks

pytestmark = pytest.mark.django_db

BASE = "/api/web/v1/settings"


class TestGroups:
    def test_crud(self, client: APIClient, company: Company) -> None:
        created = client.post(f"{BASE}/groups", {"name": "Sales"}, format="json")
        assert created.status_code == 201
        gid = created.json()["group"]["id"]

        assert client.post(f"{BASE}/groups", {"name": "Sales"}, format="json").status_code == 400

        assert client.put(f"{BASE}/groups/{gid}", {"name": "Support"}, format="json").json()[
            "success"
        ]
        assert client.get(f"{BASE}/groups").json()["groups"] == [{"id": gid, "name": "Support"}]
        assert client.delete(f"{BASE}/groups/{gid}").json()["success"]
        assert client.get(f"{BASE}/groups").json()["groups"] == []


class TestUsersAndSeats:
    def test_create_operator_returns_credentials_once(
        self, client: APIClient, company: Company
    ) -> None:
        response = client.post(
            f"{BASE}/users",
            {"user_name": "new-op", "full_name": "New Operator"},
            format="json",
        )
        assert response.status_code == 201
        creds = response.json()["credentials"]
        assert creds["user_name"] == "new-op"
        assert len(creds["password"]) >= 10
        assert len(creds["api_key"]) == 32

        # The credentials are NOT retrievable from the list endpoint.
        listing = client.get(f"{BASE}/users").json()
        assert "credentials" not in json.dumps(listing["operators"])

        # Mobile login works with the returned credentials immediately.
        mobile = APIClient().post(
            "/api/call/v1/auth",
            {"username": "new-op", "password": creds["password"]},
            format="json",
        )
        assert mobile.json() == {"success": True, "api_key": creds["api_key"]}

    def test_deactivate_toggle_hits_license_seats_instantly(
        self, client: APIClient, company: Company, op_a: OperatorProfile, op_b: OperatorProfile
    ) -> None:
        assert client.get(f"{BASE}/license").json()["seats"] == 2
        assert client.get(f"{BASE}/license").json()["total_uzs"] == 2 * 50000

        toggled = client.patch(f"{BASE}/users/{op_a.pk}", {"is_active": False}, format="json")
        assert toggled.json()["operator"]["is_active"] is False

        license_body = client.get(f"{BASE}/license").json()
        assert license_body["seats"] == 1
        assert license_body["total_uzs"] == 50000

        # Deactivated operator's mobile api_key stops working too.
        mobile = APIClient().post(
            "/api/call/v1/stats/summary",
            {"user_name": "op-a", "api_key": op_a.api_key},
            format="json",
        )
        assert mobile.status_code == 401

    def test_member_cannot_toggle(self, member_client: APIClient, op_a: OperatorProfile) -> None:
        response = member_client.patch(
            f"{BASE}/users/{op_a.pk}", {"is_active": False}, format="json"
        )
        assert response.status_code == 403


class TestDevices:
    def test_list_toggle_and_delete(
        self, client: APIClient, company: Company, op_a: OperatorProfile
    ) -> None:
        device = Device.all_objects.create(
            company=company,
            operator=op_a,
            device_id="dev-123",
            manufacturer="Xiaomi",
            model="Redmi 12",
            last_seen_at=timezone.now(),
        )
        sim = SimCard.all_objects.create(
            company=company, operator=op_a, sim_slot=0, number="+998901234567"
        )

        listing = client.get(f"{BASE}/devices").json()["devices"]
        assert listing[0]["online"] is True
        assert listing[0]["sims"][0]["recording_enabled"] is True

        updated = client.patch(
            f"{BASE}/sims/{sim.pk}",
            {"recording_enabled": False, "number": "998907654321"},
            format="json",
        ).json()["sim"]
        assert updated["recording_enabled"] is False
        assert updated["number"] == "+998907654321"  # normalized

        assert client.delete(f"{BASE}/devices/{device.pk}").json()["success"]
        assert not Device.all_objects.filter(pk=device.pk).exists()


class TestAccountToggles:
    def test_defaults_and_update(self, client: APIClient, company: Company) -> None:
        defaults = client.get(f"{BASE}/account").json()["settings"]
        assert defaults == {
            "contact_import_enabled": True,
            "recording_enabled": True,
            "pin_enabled": False,
        }
        updated = client.put(
            f"{BASE}/account", {"pin_enabled": True, "recording_enabled": False}, format="json"
        ).json()["settings"]
        assert updated["pin_enabled"] is True
        assert updated["recording_enabled"] is False
        company.refresh_from_db()
        assert company.feature_flags["pin_enabled"] is True


class TestApiKey:
    def test_generate_and_rotate(self, client: APIClient, company: Company) -> None:
        assert client.get(f"{BASE}/api-key").json()["api_key_masked"] is None
        first = client.post(f"{BASE}/api-key").json()["api_key"]
        second = client.post(f"{BASE}/api-key").json()["api_key"]
        assert first != second and len(second) == 32
        masked = client.get(f"{BASE}/api-key").json()["api_key_masked"]
        assert masked == f"{second[:6]}…"


class TestWebhook:
    def test_configure_returns_secret_once(self, client: APIClient, company: Company) -> None:
        body = client.put(
            f"{BASE}/webhook", {"url": "https://crm.example.uz/hook"}, format="json"
        ).json()
        assert body["secret"] and len(body["secret"]) == 64

        # Second save: secret NOT returned again.
        again = client.put(
            f"{BASE}/webhook", {"url": "https://crm.example.uz/hook2"}, format="json"
        ).json()
        assert again["secret"] is None
        assert client.get(f"{BASE}/webhook").json()["secret_set"] is True

    def test_fires_on_upload_with_valid_hmac(
        self,
        client: APIClient,
        company: Company,
        op_a: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        client.put(f"{BASE}/webhook", {"url": "https://crm.example.uz/hook"}, format="json")
        company.refresh_from_db()

        captured: dict[str, Any] = {}

        def fake_deliver(target_company: Company, payload: dict[str, Any], **kw: Any) -> int:
            body = json.dumps(payload).encode()
            captured["signature"] = web_tasks.sign_webhook(target_company.webhook_secret, body)
            captured["payload"] = payload
            captured["secret"] = target_company.webhook_secret
            return 200

        monkeypatch.setattr(web_tasks, "deliver_webhook", fake_deliver)
        monkeypatch.setattr(
            web_tasks.deliver_call_webhook,
            "delay",
            lambda record_id: web_tasks.deliver_call_webhook(record_id),
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = APIClient().post(
                "/api/call/v1/upload",
                {
                    "user_name": "op-a",
                    "api_key": op_a.api_key,
                    "call_id": "hook-call-1",
                    "call_type": "inbound",
                    "call_status": "answered",
                    "from": "+998901234567",
                    "to": "+998998887766",
                    "counterparty_number": "+998901234567",
                    "duration": 5,
                    "start_time": "2026-08-14 12:00:00",
                },
                format="json",
            )
        assert response.status_code == 200

        assert captured["payload"]["event"] == "call.received"
        assert captured["payload"]["call_id"] == "hook-call-1"
        # Independent HMAC verification with the company secret.
        expected = hmac.new(
            captured["secret"].encode(),
            json.dumps(captured["payload"]).encode(),
            hashlib.sha256,
        ).hexdigest()
        assert captured["signature"] == expected

    def test_test_delivery_endpoint(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client.put(f"{BASE}/webhook", {"url": "https://crm.example.uz/hook"}, format="json")
        monkeypatch.setattr(web_tasks, "deliver_webhook", lambda c, p, **kw: 204)
        # The view imported the symbol module-level? No — it calls via module.
        from apps.web import views_settings

        monkeypatch.setattr(views_settings, "deliver_webhook", lambda c, p, **kw: 204)
        assert client.post(f"{BASE}/webhook/test").json() == {
            "success": True,
            "delivery_status": 204,
        }


class TestLicense:
    def test_trial_countdown(self, client: APIClient, company: Company) -> None:
        from datetime import timedelta

        from apps.billing.models import Subscription

        company.status = Company.Status.TRIAL
        company.trial_ends_at = timezone.now() + timedelta(days=5, hours=1)
        company.save()
        Subscription.all_objects.filter(company=company).update(status="trial")

        body = client.get(f"{BASE}/license").json()
        assert body["status"] == "trial"
        assert body["trial_days_left"] == 5


class TestOperatorFullInfo:
    """Operator creation carries the full profile: name, group, SIM numbers."""

    def test_create_with_full_info(self, client: APIClient, company: Company) -> None:
        from apps.accounts.models import OperatorGroup, SimCard

        group = OperatorGroup.all_objects.create(company=company, name="Sales")
        response = client.post(
            "/api/web/v1/settings/users",
            {
                "user_name": "full-op",
                "full_name": "Aziz Karimov",
                "phone": "901234567",
                "phone2": "+998931112233",
                "group_id": group.pk,
            },
            format="json",
        )
        assert response.status_code == 201
        body = response.json()["operator"]
        assert body["full_name"] == "Aziz Karimov"
        assert body["group_id"] == group.pk
        # 9-digit local number normalized to +998…
        assert body["phones"] == [
            {"sim_slot": 0, "number": "+998901234567"},
            {"sim_slot": 1, "number": "+998931112233"},
        ]
        assert SimCard.all_objects.filter(operator__user_name="full-op").count() == 2

    def test_create_minimal_still_works(self, client: APIClient) -> None:
        response = client.post(
            "/api/web/v1/settings/users", {"user_name": "bare-op"}, format="json"
        )
        assert response.status_code == 201
        assert response.json()["operator"]["phones"] == []
