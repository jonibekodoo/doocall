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


AMO_CONFIG = {
    "base_url": "https://x.amocrm.ru",
    "access_token": "t" * 20,
    "responsible_user_id": "504141",
}


class TestAmoCrmAdapter:
    """Contract of the amoCRM sender: attach by phone, create-contact fallback."""

    def _run(
        self, monkeypatch: pytest.MonkeyPatch, call: CallRecord, responses: list[Any]
    ) -> list[tuple[str, Any]]:
        seen: list[tuple[str, Any]] = []

        def fake_http(url: str, payload: Any = None, *, headers: Any = None, method: Any = None):
            seen.append((url, payload))
            result = responses[len(seen) - 1]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(providers, "_http_json", fake_http)
        providers.send_call("amocrm", AMO_CONFIG, call, "https://rec.example/1")
        return seen

    def test_direct_success_single_request(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        landed = {
            "_total_items": 1,
            "errors": [],
            "_embedded": {"calls": [{"id": 1, "entity_id": 777, "entity_type": "contact"}]},
        }
        seen = self._run(monkeypatch, call, [landed])
        assert len(seen) == 1
        url, payload = seen[0]
        assert url.endswith("/api/v4/calls")
        row = payload[0]
        assert row["phone"] == "+998901112233"
        assert row["direction"] == "inbound"
        assert row["call_status"] == 4  # answered → разговор состоялся
        assert row["link"] == "https://rec.example/1"
        assert row["responsible_user_id"] == 504141
        assert row["uniq"] == call.server_id.hex

    def test_unknown_phone_creates_contact_and_retries(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        not_landed = {"_total_items": 0, "errors": [{"detail": "Entity not found"}], "_embedded": {"calls": []}}
        contact_created = {"_embedded": {"contacts": [{"id": 555}]}}
        landed = {"errors": [], "_embedded": {"calls": [{"id": 2, "entity_id": 555}]}}
        seen = self._run(monkeypatch, call, [not_landed, contact_created, landed])
        assert [u.rsplit("/", 1)[-1] for u, _ in seen] == ["calls", "contacts", "calls"]
        contact = seen[1][1][0]
        assert contact["name"] == "+998901112233"  # no known name → number
        assert (
            contact["custom_fields_values"][0]["values"][0]["value"] == "+998901112233"
        )
        assert contact["responsible_user_id"] == 504141

    def test_entity_not_found_as_http_400_triggers_fallback(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Live behaviour: amoCRM returns HTTP 400 + status 263 for unknown phones.
        http_400 = providers.ProviderError(
            'HTTP 400: {"_total_items":0,"errors":[{"title":"Entity not found","status":263}]}'
        )
        contact_created = {"_embedded": {"contacts": [{"id": 9}]}}
        landed = {"errors": [], "_embedded": {"calls": [{"id": 3, "entity_id": 9}]}}
        seen = self._run(monkeypatch, call, [http_400, contact_created, landed])
        assert [u.rsplit("/", 1)[-1] for u, _ in seen] == ["calls", "contacts", "calls"]

    def test_other_http_400_is_raised(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(providers.ProviderError, match="401"):
            self._run(monkeypatch, call, [providers.ProviderError("HTTP 401: bad token")])

    def test_raises_when_retry_also_fails(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        not_landed = {"errors": [{"detail": "nope"}], "_embedded": {"calls": []}}
        contact_created = {"_embedded": {"contacts": [{"id": 5}]}}
        with pytest.raises(providers.ProviderError, match="rejected"):
            self._run(monkeypatch, call, [not_landed, contact_created, not_landed])

    def test_contact_creation_failure_raises(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        not_landed = {"errors": [], "_embedded": {"calls": []}}
        with pytest.raises(providers.ProviderError, match="could not be created"):
            self._run(monkeypatch, call, [not_landed, {"_embedded": {"contacts": []}}])


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
