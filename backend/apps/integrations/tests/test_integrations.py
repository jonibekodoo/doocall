"""Functional coverage: cabinet integration settings, dispatch task, public API."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db

BASE = "/api/web/v1/settings/integrations"


class TestCabinetSettings:
    def test_list_shows_all_providers_masked(self, client: APIClient, company: Company) -> None:
        CrmIntegration.all_objects.create(
            company=company,
            provider="amocrm",
            is_enabled=True,
            config={"base_url": "https://x.amocrm.ru", "access_token": "secret-token-abcdef"},
        )
        body = client.get(BASE).json()
        by_provider = {row["provider"]: row for row in body["integrations"]}
        assert set(by_provider) == {"amocrm", "bitrix24", "odoo"}
        amo = by_provider["amocrm"]
        assert amo["is_enabled"] is True
        assert "secret-token-abcdef" not in str(amo)
        assert amo["config"]["access_token"].startswith("secr")
        assert by_provider["odoo"]["configured"] is False

    def test_save_validates_and_preserves_masked_secret(
        self, client: APIClient, company: Company
    ) -> None:
        # Enabling without required fields → 400.
        response = client.put(
            f"{BASE}/odoo",
            {"is_enabled": True, "config": {"url": "https://erp.x.uz"}},
            format="json",
        )
        assert response.status_code == 400

        saved = client.put(
            f"{BASE}/odoo",
            {
                "is_enabled": True,
                "config": {
                    "url": "https://erp.x.uz",
                    "db": "prod",
                    "login": "bot@x.uz",
                    "api_key": "odoo-key-123456",
                },
            },
            format="json",
        )
        assert saved.status_code == 200

        # Re-saving with the masked echo keeps the stored secret.
        masked = saved.json()["integration"]["config"]["api_key"]
        assert "…" in masked or masked == "•••"
        client.put(
            f"{BASE}/odoo",
            {"is_enabled": True, "config": {"url": "https://erp2.x.uz", "api_key": masked}},
            format="json",
        )
        row = CrmIntegration.all_objects.get(company=company, provider="odoo")
        assert row.config["api_key"] == "odoo-key-123456"
        assert row.config["url"] == "https://erp2.x.uz"

    def test_member_cannot_manage(self, company: Company) -> None:
        member = User.objects.create_user(
            username="member@integr-co.uz", company=company, is_company_admin=False
        )
        api = APIClient()
        api.force_authenticate(user=member)
        assert api.get(BASE).status_code == 403


class TestDispatch:
    def test_dispatch_records_status_per_integration(
        self, company: Company, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok = CrmIntegration.all_objects.create(
            company=company,
            provider="amocrm",
            is_enabled=True,
            config={"base_url": "https://x.amocrm.ru", "access_token": "t" * 20},
        )
        bad = CrmIntegration.all_objects.create(
            company=company,
            provider="odoo",
            is_enabled=True,
            config={"url": "https://erp.x.uz", "db": "d", "login": "l", "api_key": "k" * 20},
        )
        sent: list[str] = []

        def fake_send(provider: str, config: dict[str, Any], record: Any, url: Any) -> None:
            if provider == "odoo":
                raise providers.ProviderError("boom")
            sent.append(provider)

        monkeypatch.setattr(providers, "send_call", fake_send)
        assert tasks.dispatch_call(call.pk) == 1
        ok.refresh_from_db()
        bad.refresh_from_db()
        assert sent == ["amocrm"]
        assert ok.last_status == "ok" and ok.last_error == ""
        assert bad.last_status == "error" and "boom" in bad.last_error

    def test_public_record_url_is_permanent_and_signed(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch, client: APIClient
    ) -> None:
        from apps.api import storage

        url = tasks.public_record_url(call)
        assert url is not None and "/api/public/rec/" in url and "sig=" in url

        monkeypatch.setattr(storage, "presigned_url", lambda key: f"https://s3.test/{key}")
        path = url[url.index("/api/public/rec/") :]
        good = client.get(path)
        assert good.status_code == 302
        assert good["Location"].startswith("https://s3.test/")
        assert client.get(path.split("?")[0] + "?sig=wrong").status_code == 403


class TestPublicApi:
    def _post(self, client: APIClient, payload: dict[str, Any]) -> Any:
        return client.post("/api/v1", payload, format="json")

    def test_auth_and_calls_list(
        self, company: Company, admin_user: User, call: CallRecord
    ) -> None:
        api = APIClient()
        assert (
            self._post(api, {"user_name": "admin@integr-co.uz", "api_key": "nope", "action": "x"})
            .status_code
            == 401
        )
        assert (
            self._post(
                api,
                {
                    "user_name": "ghost@x.uz",
                    "api_key": "companykey123456",
                    "action": "calls.list",
                },
            ).status_code
            == 401
        )

        body = self._post(
            api,
            {
                "user_name": "admin@integr-co.uz",
                "api_key": "companykey123456",
                "action": "calls.list",
                "limit": 10,
            },
        ).json()
        assert body["success"] is True and body["total"] == 1
        row = body["calls"][0]
        assert row["call_id"] == "c-1"
        assert row["operator"] == "op-1"
        assert row["record_url"] and "/api/public/rec/" in row["record_url"]

    def test_calls_get_and_users_list(
        self, company: Company, admin_user: User, call: CallRecord
    ) -> None:
        api = APIClient()
        auth = {"user_name": "admin@integr-co.uz", "api_key": "companykey123456"}
        one = self._post(api, {**auth, "action": "calls.get", "call_id": "c-1"}).json()
        assert one["call"]["counterparty_number"] == "+998901112233"

        users = self._post(api, {**auth, "action": "users.list"}).json()
        assert [u["user_name"] for u in users["users"]] == ["op-1"]

        info = self._post(api, {**auth, "action": "account.info"}).json()
        assert info["account"]["slug"] == "integr-co"

        assert self._post(api, {**auth, "action": "nope"}).status_code == 400


class TestCrmCatalog:
    def test_admin_crud_and_cabinet_list(
        self, client: APIClient, company: Company, db: Any
    ) -> None:
        from apps.integrations.models import CrmCatalogEntry

        CrmCatalogEntry.objects.create(name="EnvyCRM", site_url="https://envycrm.com")
        CrmCatalogEntry.objects.create(
            name="HiddenCRM", site_url="https://hidden.io", is_active=False
        )
        body = client.get(f"{BASE}/catalog").json()
        assert [e["name"] for e in body["entries"]] == ["EnvyCRM"]
