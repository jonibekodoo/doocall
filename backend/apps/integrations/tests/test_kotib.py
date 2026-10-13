"""Kotib Analytics connector: connect/disconnect via the cabinet, signed
call.received delivery through the CRM dispatcher. HTTP is faked at
``urllib.request.urlopen`` — every request Kotib would see is recorded."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import urllib.error
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.integrations import tasks
from apps.integrations.models import CrmDelivery, CrmIntegration
from apps.web.tasks import webhook_payload

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/integrations/kotib"
KOTIB = "https://kotib.test/api/v1/integration/doocall"
KOTIB_KEY = "kotib-secret-key-0123456789"
HOOK = "https://kotib.test/api/v1/integration/doocall/Xk3tokenq9/webhook"

CONNECTED = {
    "success": True,
    "company": "My Company",
    "webhook_url": HOOK,
    "employees": {"created": 12, "existing": 1, "created_inactive": 2},
}


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _http_error(status: int, body: dict[str, Any] | None = None) -> urllib.error.HTTPError:
    raw = json.dumps(body).encode() if body is not None else b""
    return urllib.error.HTTPError(HOOK, status, "err", {}, io.BytesIO(raw))  # type: ignore[arg-type]


class FakeKotib:
    """Queue of responses (dict → 200 JSON, int/tuple → HTTPError)."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: int = 0) -> _Response:
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, tuple):
            raise _http_error(*result)
        if isinstance(result, int):
            raise _http_error(result)
        return _Response(json.dumps(result).encode())

    def json(self, index: int) -> dict[str, Any]:
        return json.loads(self.requests[index].data)


@pytest.fixture
def kotib(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(*responses: Any) -> FakeKotib:
        fake = FakeKotib(*responses)
        monkeypatch.setattr("urllib.request.urlopen", fake)
        return fake

    with override_settings(KOTIB_BASE_URL=KOTIB):
        yield install


def _connect(client: APIClient, api_key: str = KOTIB_KEY) -> Any:
    return client.put(URL, {"is_enabled": True, "config": {"api_key": api_key}}, format="json")


def _row(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.get(company=company, provider="kotib")


class TestConnect:
    def test_success_stores_config_and_hides_secrets(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        company.webhook_url = "https://customer.example/hook"
        company.webhook_secret = "customer-secret"
        company.save()
        fake = kotib(CONNECTED)

        response = _connect(client)

        assert response.status_code == 200
        request = fake.requests[0]
        assert request.full_url == f"{KOTIB}/connect"
        assert request.get_method() == "POST"
        assert request.get_header("X-api-key") == KOTIB_KEY
        sent = fake.json(0)
        assert sent["account"] == "integr-co"
        assert sent["user_name"] == "admin@integr-co.uz"
        assert sent["api_key"] == "companykey123456"
        assert len(sent["webhook_secret"]) == 64

        row = _row(company)
        assert row.is_enabled is True and row.last_status == "ok"
        assert row.config["api_key"] == KOTIB_KEY
        assert row.config["webhook_url"] == HOOK
        assert row.config["webhook_secret"] == sent["webhook_secret"]

        body = response.json()["integration"]
        assert body["is_enabled"] is True
        assert body["config"] == {
            "api_key": "koti…6789",
            "company_name": "My Company",
            "employees_created": 12,
            "employees_existing": 1,
            "employees_created_inactive": 2,
        }
        listing = client.get("/api/web/v1/settings/integrations").json()
        for text in (str(body), str(listing)):
            assert KOTIB_KEY not in text
            assert "Xk3tokenq9" not in text
            assert sent["webhook_secret"] not in text

        # The customer's own "custom" webhook is untouched.
        company.refresh_from_db()
        assert company.webhook_url == "https://customer.example/hook"
        assert company.webhook_secret == "customer-secret"

        audit = AuditLog.objects.filter(action="settings.integration_saved").get()
        assert KOTIB_KEY not in json.dumps(audit.changes)
        assert sent["webhook_secret"] not in json.dumps(audit.changes)

    def test_null_employees_is_still_connected(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        kotib({**CONNECTED, "employees": None})
        body = _connect(client).json()["integration"]
        assert body["is_enabled"] is True
        assert body["config"]["employees_created"] is None

    def test_generates_company_api_key_when_missing(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        company.api_key = ""
        company.save()
        fake = kotib(CONNECTED)
        assert _connect(client).status_code == 200
        company.refresh_from_db()
        assert len(company.api_key) == 32
        assert fake.json(0)["api_key"] == company.api_key

    @pytest.mark.parametrize(
        ("status", "code", "message", "expected"),
        [
            (401, "INVALID_API_KEY", "", "Kotib API kaliti noto'g'ri"),
            (400, "MISSING_FIELD", "user_name is required", "user_name is required"),
            (400, "INVALID_ACCOUNT", "bad account", "bad account"),
            (400, "DOOCALL_AUTH_FAILED", "DooCall rejected the key", "DooCall rejected the key"),
            (502, "DOOCALL_UNAVAILABLE", "", "birozdan keyin qayta urinib"),
        ],
    )
    def test_errors_return_400_with_message_and_enable_nothing(
        self,
        client: APIClient,
        company: Company,
        kotib: Any,
        status: int,
        code: str,
        message: str,
        expected: str,
    ) -> None:
        kotib((status, {"success": False, "error_code": code, "message": message}))
        response = _connect(client)
        assert response.status_code == 400
        assert expected in response.json()["message"]
        assert KOTIB_KEY not in response.json()["message"]
        assert not CrmIntegration.all_objects.filter(company=company, is_enabled=True).exists()
        assert not CrmIntegration.all_objects.filter(company=company, provider="kotib").exists()

    def test_failed_resave_keeps_previous_secret(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        kotib(CONNECTED, (401, {"success": False, "error_code": "INVALID_API_KEY"}))
        _connect(client)
        before = dict(_row(company).config)
        assert _connect(client, "another-wrong-key-123").status_code == 400
        assert _row(company).config == before

    def test_missing_key_is_400_without_calling_kotib(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib()
        response = client.put(URL, {"is_enabled": True, "config": {}}, format="json")
        assert response.status_code == 400 and fake.requests == []

    def test_resave_with_masked_key_rotates_secret(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib(CONNECTED, CONNECTED)
        masked = _connect(client).json()["integration"]["config"]["api_key"]
        first = _row(company).config["webhook_secret"]

        assert _connect(client, masked).status_code == 200

        assert fake.requests[1].get_header("X-api-key") == KOTIB_KEY  # stored key reused
        second = _row(company).config["webhook_secret"]
        assert second != first and fake.json(1)["webhook_secret"] == second

    def test_test_endpoint_reconnects_with_stored_secret(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib(CONNECTED, CONNECTED)
        _connect(client)
        secret = _row(company).config["webhook_secret"]
        response = client.post(f"{URL}/test")
        assert response.status_code == 200 and response.json()["detail"] == "My Company"
        assert fake.json(1)["webhook_secret"] == secret


class TestDisconnect:
    def test_delete_calls_kotib_and_wipes(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib(CONNECTED, {"success": True})
        _connect(client)
        response = client.delete(URL)
        assert response.status_code == 200
        request = fake.requests[1]
        assert request.full_url == f"{KOTIB}/disconnect"
        assert request.get_header("X-api-key") == KOTIB_KEY
        assert fake.json(1) == {"account": "integr-co"}
        row = _row(company)
        assert row.is_enabled is False and row.config == {}

    def test_not_found_on_kotib_side_is_fine(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        kotib(CONNECTED, (404, {"success": False, "error_code": "NOT_FOUND"}))
        _connect(client)
        assert client.delete(URL).status_code == 200
        assert _row(company).config == {}

    def test_kotib_failure_still_wipes_locally(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        kotib(CONNECTED, (401, {"success": False, "error_code": "INVALID_API_KEY"}))
        _connect(client)
        assert client.delete(URL).status_code == 200
        row = _row(company)
        assert row.is_enabled is False and row.config == {}

    def test_save_disabled_equals_disconnect(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib(CONNECTED, {"success": True})
        _connect(client)
        response = client.put(URL, {"is_enabled": False}, format="json")
        assert response.status_code == 200
        assert fake.requests[1].full_url == f"{KOTIB}/disconnect"
        assert _row(company).config == {} and _row(company).is_enabled is False


class TestDelivery:
    @pytest.fixture
    def connected(self, company: Company) -> CrmIntegration:
        return CrmIntegration.all_objects.create(
            company=company,
            provider="kotib",
            is_enabled=True,
            config={"api_key": KOTIB_KEY, "webhook_url": HOOK, "webhook_secret": "s3cr3t" * 4},
        )

    def test_sends_signed_payload(
        self, connected: CrmIntegration, call: CallRecord, company: Company, kotib: Any
    ) -> None:
        company.webhook_url = "https://customer.example/hook"
        company.save()
        fake = kotib({"success": True})

        assert tasks.dispatch_call(call.pk) == 1

        request = fake.requests[0]
        assert request.full_url == HOOK
        raw: bytes = request.data
        expected = hmac.new(b"s3cr3t" * 4, raw, hashlib.sha256).hexdigest()
        assert request.get_header("X-doocall-signature") == expected
        assert json.loads(raw) == json.loads(json.dumps(webhook_payload(call)))
        assert json.loads(raw)["server_id"] == f"srv_{call.server_id.hex}"
        delivery = CrmDelivery.all_objects.get(call=call, provider="kotib")
        assert delivery.status == "ok"
        company.refresh_from_db()
        assert company.webhook_url == "https://customer.example/hook"

    @pytest.mark.parametrize(
        ("status", "duration"), [("no_answer", 0), ("busy", 0), ("answered", 0)]
    )
    def test_skips_unanswered_and_zero_duration(
        self,
        connected: CrmIntegration,
        call: CallRecord,
        kotib: Any,
        status: str,
        duration: int,
    ) -> None:
        CallRecord.all_objects.filter(pk=call.pk).update(call_status=status, duration=duration)
        fake = kotib()
        assert tasks.dispatch_call(call.pk) == 0
        assert fake.requests == []
        assert not CrmDelivery.all_objects.filter(call=call).exists()

    def test_gone_disables_integration(
        self, connected: CrmIntegration, call: CallRecord, kotib: Any
    ) -> None:
        kotib(410)
        assert tasks.dispatch_call(call.pk) == 0
        connected.refresh_from_db()
        assert connected.is_enabled is False
        assert connected.last_status == "error"
        assert connected.last_error == "Kotib: integratsiya o'chirilgan (410)"
        delivery = CrmDelivery.all_objects.get(call=call, provider="kotib")
        assert delivery.status == "error"

    def test_bad_signature_asks_to_resave_without_leaking_url(
        self, connected: CrmIntegration, call: CallRecord, kotib: Any
    ) -> None:
        kotib(401)
        tasks.dispatch_call(call.pk)
        connected.refresh_from_db()
        assert connected.is_enabled is True
        assert "re-save" in connected.last_error
        assert "Xk3tokenq9" not in connected.last_error

    def test_transient_error_keeps_integration_enabled(
        self, connected: CrmIntegration, call: CallRecord, kotib: Any
    ) -> None:
        kotib(503)
        tasks.dispatch_call(call.pk)
        connected.refresh_from_db()
        assert connected.is_enabled is True and connected.last_error == "Kotib: HTTP 503"
