"""Kotib Analytics connector: connect/disconnect via the cabinet, signed
call.received delivery through the CRM dispatcher. HTTP is faked at
``providers._kotib_open`` (the no-redirect opener) — every request Kotib
would see is recorded."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.integrations import providers, tasks
from apps.integrations.models import CrmDelivery, CrmIntegration
from apps.web.tasks import webhook_payload

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/integrations/kotib"
KOTIB = "https://kotib.test/api/v1/integration/doocall"
KOTIB_KEY = "kotib-secret-key-0123456789"
HOOK = "https://kotib.test/api/v1/integration/doocall/Xk3tokenq9/webhook"

DOOCALL_KEY = "d" * 32
PUBLIC = "/api/v1"

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
    """Queue of responses (dict → 200 JSON, int/tuple → HTTPError,
    exception instance → raised as-is)."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[Any] = []

    def __call__(self, request: Any) -> _Response:
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
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
        monkeypatch.setattr(providers, "_kotib_open", fake)
        return fake

    with override_settings(KOTIB_BASE_URL=KOTIB):
        yield install


def _connect(client: APIClient, api_key: str = KOTIB_KEY) -> Any:
    return client.put(URL, {"is_enabled": True, "config": {"api_key": api_key}}, format="json")


def _row(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.get(company=company, provider="kotib")


def _assert_never_connected(company: Company) -> None:
    """A failed first connect leaves (at most) a disabled, empty row."""
    for row in CrmIntegration.all_objects.filter(company=company, provider="kotib"):
        assert row.is_enabled is False and row.config == {}


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
        # Kotib gets its own key, never the company-wide one.
        assert len(sent["api_key"]) == 32 and sent["api_key"] != "companykey123456"
        assert len(sent["webhook_secret"]) == 64

        row = _row(company)
        assert row.is_enabled is True and row.last_status == "ok"
        assert row.config["api_key"] == KOTIB_KEY
        assert row.config["webhook_url"] == HOOK
        assert row.config["webhook_secret"] == sent["webhook_secret"]
        assert row.config["doocall_api_key"] == sent["api_key"]

        body = response.json()["integration"]
        assert body["is_enabled"] is True
        analysis_url = body["config"].pop("analysis_webhook_url")
        assert analysis_url.endswith(row.config["analysis_token"])
        assert body["config"] == {
            "api_key": "koti…6789",
            "company_name": "My Company",
            "employees_created": 12,
            "employees_existing": 1,
            "employees_created_inactive": 2,
            "analysis_secret": "",
            "analysis_last_received_at": None,
            "analysis_count": 0,
        }
        listing = client.get("/api/web/v1/settings/integrations").json()
        for text in (str(body), str(listing)):
            assert KOTIB_KEY not in text
            assert "Xk3tokenq9" not in text
            assert sent["webhook_secret"] not in text
            assert sent["api_key"] not in text

        # The customer's own "custom" webhook is untouched.
        company.refresh_from_db()
        assert company.webhook_url == "https://customer.example/hook"
        assert company.webhook_secret == "customer-secret"

        audit = AuditLog.objects.filter(action="settings.integration_saved").get()
        for secret in (KOTIB_KEY, sent["webhook_secret"], sent["api_key"]):
            assert secret not in json.dumps(audit.changes)

    def test_null_employees_is_still_connected(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        kotib({**CONNECTED, "employees": None})
        body = _connect(client).json()["integration"]
        assert body["is_enabled"] is True
        assert body["config"]["employees_created"] is None

    def test_company_api_key_is_never_created_or_changed(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        company.api_key = ""
        company.save()
        fake = kotib(CONNECTED, {"success": True})
        assert _connect(client).status_code == 200
        client.delete(URL)
        company.refresh_from_db()
        assert company.api_key == ""
        assert len(fake.json(0)["api_key"]) == 32

    def test_resave_keeps_doocall_key_new_kotib_key_rotates_it(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        fake = kotib(CONNECTED, CONNECTED, CONNECTED)
        masked = _connect(client).json()["integration"]["config"]["api_key"]
        first = _row(company).config["doocall_api_key"]
        _connect(client, masked)
        assert _row(company).config["doocall_api_key"] == first
        assert fake.json(1)["api_key"] == first
        _connect(client, "a-different-kotib-key-999")
        assert _row(company).config["doocall_api_key"] not in ("", first)

    @pytest.mark.parametrize(
        "hook",
        [
            "http://kotib.test/api/v1/integration/doocall/x/webhook",
            "https://evil.test/api/v1/integration/doocall/x/webhook",
            "https://kotib.test.evil.test/api/v1/integration/doocall/x/webhook",
            "https://kotib.test:8443/api/v1/integration/doocall/x/webhook",
            "https://user@kotib.test/api/v1/integration/doocall/x/webhook",
            "https://kotib.test/api/v1/other/x/webhook",
            "https://kotib.test/api/v1/integration/doocall/../../admin",
            "https://kotib.test/api/v1/integration/doocallx/webhook",
            "https://169.254.169.254/latest/meta-data",
        ],
    )
    def test_webhook_url_outside_kotib_base_is_rejected(
        self, client: APIClient, company: Company, kotib: Any, hook: str
    ) -> None:
        kotib({**CONNECTED, "webhook_url": hook})
        response = _connect(client)
        assert response.status_code == 400
        assert "webhook_url" in response.json()["message"]
        _assert_never_connected(company)

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
        _assert_never_connected(company)

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
        assert fake.json(1)["api_key"] == _row(company).config["doocall_api_key"]


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
            config={
                "api_key": KOTIB_KEY,
                "webhook_url": HOOK,
                "webhook_secret": "s3cr3t" * 4,
                "doocall_api_key": DOOCALL_KEY,
            },
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

    def test_gone_revokes_public_api_key(
        self, connected: CrmIntegration, call: CallRecord, admin_user: Any, kotib: Any
    ) -> None:
        api = APIClient()
        auth = {"user_name": "admin@integr-co.uz", "api_key": DOOCALL_KEY}
        assert (
            api.post(PUBLIC, {**auth, "action": "account.info"}, format="json").status_code == 200
        )
        kotib(410)
        tasks.dispatch_call(call.pk)
        connected.refresh_from_db()
        assert "doocall_api_key" not in connected.config
        assert (
            api.post(PUBLIC, {**auth, "action": "account.info"}, format="json").status_code == 401
        )

    def test_tampered_stored_url_is_not_called(
        self, connected: CrmIntegration, call: CallRecord, kotib: Any
    ) -> None:
        connected.config = {**connected.config, "webhook_url": "https://evil.test/hook"}
        connected.save()
        fake = kotib()
        tasks.dispatch_call(call.pk)
        connected.refresh_from_db()
        assert fake.requests == [] and "webhook_url" in connected.last_error


class TestKotibPublicApiKey:
    """Kotib's own key: read-only actions, only while the integration is on."""

    def _post(self, api: APIClient, key: str, action: str, **extra: Any) -> Any:
        return api.post(
            PUBLIC,
            {"user_name": "admin@integr-co.uz", "api_key": key, "action": action, **extra},
            format="json",
        )

    def _connect(self, client: APIClient, kotib: Any) -> str:
        fake = kotib(CONNECTED, {"success": True})
        assert _connect(client).status_code == 200
        return str(fake.json(0)["api_key"])

    def test_key_works_while_connected(
        self, client: APIClient, company: Company, call: CallRecord, kotib: Any
    ) -> None:
        key = self._connect(client, kotib)
        api = APIClient()
        assert self._post(api, key, "account.info").json()["account"]["slug"] == "integr-co"
        assert self._post(api, key, "users.list").status_code == 200
        assert self._post(api, key, "calls.list").json()["total"] == 1
        assert self._post(api, key, "calls.get", call_id="c-1").status_code == 200

    def test_only_read_actions_are_allowed(
        self, client: APIClient, company: Company, kotib: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = self._connect(client, kotib)
        response = self._post(APIClient(), key, "calls.delete")
        assert response.status_code == 403
        # Even an action the company key may use is refused if not allow-listed.
        from apps.integrations import views_public

        monkeypatch.setattr(views_public, "KOTIB_ALLOWED_ACTIONS", frozenset({"users.list"}))
        assert self._post(APIClient(), key, "account.info").status_code == 403
        assert self._post(APIClient(), key, "users.list").status_code == 200

    def test_key_dies_on_disconnect(self, client: APIClient, company: Company, kotib: Any) -> None:
        key = self._connect(client, kotib)
        assert client.delete(URL).status_code == 200
        assert self._post(APIClient(), key, "account.info").status_code == 401

    def test_key_dies_when_disabled_or_saved_off(
        self, client: APIClient, company: Company, kotib: Any
    ) -> None:
        key = self._connect(client, kotib)
        CrmIntegration.all_objects.filter(company=company).update(is_enabled=False)
        assert self._post(APIClient(), key, "account.info").status_code == 401

    def test_key_is_bound_to_its_company(
        self, client: APIClient, company: Company, kotib: Any, settings: Any
    ) -> None:
        settings.DOMAIN_ROOT = "doocall.uz"
        key = self._connect(client, kotib)
        other = Company.objects.create(name="Other", slug="other-co", status=company.status)
        from apps.accounts.models import User

        User.objects.create_user(username="boss@other.uz", email="boss@other.uz", company=other)
        response = APIClient().post(
            PUBLIC,
            {"user_name": "boss@other.uz", "api_key": key, "action": "account.info"},
            format="json",
        )
        assert response.status_code == 401
        wrong_host = APIClient().post(
            PUBLIC,
            {"user_name": "admin@integr-co.uz", "api_key": key, "action": "account.info"},
            format="json",
            HTTP_HOST="other-co.doocall.uz",
        )
        assert wrong_host.status_code == 401
        right_host = APIClient().post(
            PUBLIC,
            {"user_name": "admin@integr-co.uz", "api_key": key, "action": "account.info"},
            format="json",
            HTTP_HOST="integr-co.doocall.uz",
        )
        assert right_host.status_code == 200


class _Redirector(BaseHTTPRequestHandler):
    hits: list[tuple[str, str | None]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        _Redirector.hits.append((self.path, self.headers.get("X-API-Key")))
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:9/stolen")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


class TestNoRedirects:
    """Real HTTP: the Kotib opener must refuse 3xx instead of following it."""

    @pytest.fixture
    def server(self) -> Any:
        _Redirector.hits = []
        httpd = HTTPServer(("127.0.0.1", 0), _Redirector)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_port}"
        httpd.shutdown()

    def test_connect_does_not_follow_redirect(self, server: str) -> None:
        with (
            override_settings(KOTIB_BASE_URL=f"{server}/kotib"),
            pytest.raises(providers.KotibError) as exc,
        ):
            providers.kotib_connect(KOTIB_KEY, "integr-co", "a@b.uz", "k" * 32, "s" * 64)
        assert exc.value.status == 302
        assert _Redirector.hits == [("/kotib/connect", KOTIB_KEY)]  # only the original hop

    def test_cabinet_connect_redirect_saves_nothing(
        self, server: str, client: APIClient, company: Company
    ) -> None:
        with override_settings(KOTIB_BASE_URL=f"{server}/kotib"):
            response = _connect(client)
        assert response.status_code == 400
        message = response.json()["message"]
        assert KOTIB_KEY not in message and "stolen" not in message
        _assert_never_connected(company)
        assert _Redirector.hits == [("/kotib/connect", KOTIB_KEY)]

    def test_disconnect_does_not_follow_redirect(self, server: str) -> None:
        with (
            override_settings(KOTIB_BASE_URL=f"{server}/kotib"),
            pytest.raises(providers.KotibError),
        ):
            providers.kotib_disconnect(KOTIB_KEY, "integr-co")
        assert _Redirector.hits == [("/kotib/disconnect", KOTIB_KEY)]

    def test_webhook_send_does_not_follow_redirect(
        self, server: str, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The stored-URL pin needs https; bypass it to exercise the opener itself.
        monkeypatch.setattr(providers, "kotib_webhook_url_ok", lambda url: True)
        config = {
            "api_key": KOTIB_KEY,
            "webhook_url": f"{server}/hook",
            "webhook_secret": "s" * 64,
            "doocall_api_key": DOOCALL_KEY,
        }
        with pytest.raises(providers.ProviderError, match="redirect refused"):
            providers.send_call("kotib", config, call, None)
        assert [path for path, _ in _Redirector.hits] == ["/hook"]


class TestConnectCallback:
    """Kotib verifies the candidate key via our public API *while* connect is
    in flight — it must already authenticate then (pending key)."""

    AUTH_USER = "admin@integr-co.uz"

    def _public(self, key: str, action: str) -> int:
        response = APIClient().post(
            PUBLIC,
            {"user_name": self.AUTH_USER, "api_key": key, "action": action},
            format="json",
        )
        return int(response.status_code)

    def _fake_connect(
        self,
        monkeypatch: pytest.MonkeyPatch,
        seen: list[dict[str, Any]],
        *,
        fail: bool = False,
        during: Any = None,
        probe_keys: tuple[str, ...] = (),
    ) -> None:
        def fake(kotib_key: str, account: str, user_name: str, key: str, secret: str) -> Any:
            if during is not None:
                during(key)
            seen.append(
                {
                    "key": key,
                    "user_name": user_name,
                    "account.info": self._public(key, "account.info"),
                    "users.list": self._public(key, "users.list"),
                    "probes": {probe: self._public(probe, "account.info") for probe in probe_keys},
                }
            )
            if fail:
                raise providers.KotibError("DooCall rejected", code="DOOCALL_AUTH_FAILED")
            return {"company": "My Company", "webhook_url": HOOK, "employees": None}

        monkeypatch.setattr(providers, "kotib_connect", fake)

    def test_callback_succeeds_during_connect_and_key_keeps_working(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[dict[str, Any]] = []
        self._fake_connect(monkeypatch, seen)
        response = _connect(client)
        assert response.status_code == 200
        call = seen[0]
        assert call["user_name"] == self.AUTH_USER
        assert call["account.info"] == 200 and call["users.list"] == 200

        row = _row(company)
        assert row.config["doocall_api_key"] == call["key"]
        assert not any(k.startswith("pending_") for k in row.config)
        assert "pending" not in json.dumps(response.json())
        assert self._public(call["key"], "account.info") == 200

    def test_expired_pending_key_is_rejected(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def expire(key: str) -> None:
            row = _row(company)
            row.config = {
                **row.config,
                "pending_doocall_api_key_until": "2000-01-01T00:00:00+00:00",
            }
            row.save()

        seen: list[dict[str, Any]] = []
        self._fake_connect(monkeypatch, seen, fail=True, during=expire)
        assert _connect(client).status_code == 400
        assert seen[0]["account.info"] == 401

    def test_pending_key_dies_after_failed_connect(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[dict[str, Any]] = []
        self._fake_connect(monkeypatch, seen, fail=True)
        response = _connect(client)
        assert response.status_code == 400
        assert seen[0]["account.info"] == 200  # it was usable while in flight
        assert self._public(seen[0]["key"], "account.info") == 401
        _assert_never_connected(company)
        assert response.json()["message"] == "DooCall rejected"

    def test_resave_keeps_old_key_and_rotates_only_on_success(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[dict[str, Any]] = []
        self._fake_connect(monkeypatch, seen)
        masked = _connect(client).json()["integration"]["config"]["api_key"]
        old = seen[0]["key"]

        # Plain re-save: same key reused, works throughout.
        self._fake_connect(monkeypatch, seen, probe_keys=(old,))
        assert _connect(client, masked).status_code == 200
        assert seen[1]["key"] == old and seen[1]["probes"][old] == 200

        # New Kotib key but Kotib fails: old key keeps working, candidate dies.
        self._fake_connect(monkeypatch, seen, fail=True, probe_keys=(old,))
        assert _connect(client, "another-kotib-key-0001").status_code == 400
        failed = seen[2]["key"]
        assert failed != old and seen[2]["probes"][old] == 200
        assert seen[2]["account.info"] == 200
        assert self._public(old, "account.info") == 200
        assert self._public(failed, "account.info") == 401
        assert _row(company).is_enabled is True

        # New Kotib key, success: rotated — old key revoked, new one active.
        self._fake_connect(monkeypatch, seen, probe_keys=(old,))
        assert _connect(client, "another-kotib-key-0001").status_code == 200
        new = seen[3]["key"]
        assert new not in (old, failed) and seen[3]["probes"][old] == 200
        assert self._public(old, "account.info") == 401
        assert self._public(new, "account.info") == 200
