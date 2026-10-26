"""Remote Dial for integrations: public API calls.dial / calls.dial.status
and Bitrix24 click-to-call (ONEXTERNALCALLSTART) incl. CALL_ID reuse."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.dial import services as dial
from apps.dial.models import DialCommand
from apps.integrations import providers, tasks
from apps.integrations.models import CrmDelivery, CrmIntegration

pytestmark = pytest.mark.django_db

API = "/api/v1"
AUTH = {"user_name": "admin@integr-co.uz", "api_key": "companykey123456"}
HOOK = "https://acme.bitrix24.ru/rest/1/tok/"
C2C = "/api/public/bitrix24/click-to-call/"


class FakeLayer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def group_send(self, group: str, message: dict[str, Any]) -> None:
        self.sent.append((group, message))


@pytest.fixture(autouse=True)
def _isolated(settings: Any, monkeypatch: pytest.MonkeyPatch) -> FakeLayer:
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": uuid.uuid4().hex,
        }
    }
    layer = FakeLayer()
    monkeypatch.setattr(dial, "get_channel_layer", lambda: layer)
    return layer


@pytest.fixture
def layer(_isolated: FakeLayer) -> FakeLayer:
    return _isolated


def go_online(op: OperatorProfile, device_id: str = "phone0001") -> None:
    Device.all_objects.get_or_create(
        company=op.company, operator=op, device_id=device_id, defaults={"model": "A54"}
    )
    dial.mark_online(
        dial.DeviceSession(
            op.company_id, op.pk, device_id, f"chan-{device_id}", dial.key_hash(op.api_key)
        ),
        timezone.now().isoformat(),
    )


def enable_api_dial(company: Company) -> None:
    company.feature_flags = {**(company.feature_flags or {}), "api_dial_enabled": True}
    company.save()


def api(body: dict[str, Any]) -> Any:
    return APIClient().post(API, {**AUTH, **body}, format="json")


def dial_frames(layer: FakeLayer) -> list[dict[str, Any]]:
    return [m["payload"] for _, m in layer.sent if m.get("type") == "dial.command"]


# ── Public API ────────────────────────────────────────────────────────────
class TestPublicApiDial:
    def test_disabled_by_default(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        go_online(operator)
        for body in (
            {"action": "calls.dial", "operator": "op-1", "number": "+998901234567"},
            {"action": "calls.dial.status", "command_id": str(uuid.uuid4())},
        ):
            response = api(body)
            assert response.status_code == 403
            assert response.json()["error_code"] == "feature_disabled"
        assert not DialCommand.all_objects.exists()

    def test_account_flag_toggle(self, client: APIClient, company: Company) -> None:
        url = "/api/web/v1/settings/account"
        assert client.get(url).json()["settings"]["api_dial_enabled"] is False
        assert (
            client.put(url, {"api_dial_enabled": True}, format="json").json()["settings"][
                "api_dial_enabled"
            ]
            is True
        )
        company.refresh_from_db()
        assert company.feature_flags["api_dial_enabled"] is True

    def test_online_dial_sent(
        self, company: Company, admin_user: User, operator: OperatorProfile, layer: FakeLayer
    ) -> None:
        enable_api_dial(company)
        go_online(operator)
        response = api({"action": "calls.dial", "operator": "op-1", "number": "90 123 45 67"})
        assert response.status_code == 200, response.content
        body = response.json()
        assert body["success"] is True and body["status"] == "sent"
        frame = dial_frames(layer)[0]
        assert frame["command_id"] == body["command_id"]
        assert frame["number"] == "+998901234567"
        assert frame["requested_by"] == "admin@integr-co.uz"
        assert layer.sent[0][0] == dial.group_name(company.pk, operator.pk, "phone0001")
        command = DialCommand.all_objects.get()
        assert command.created_by == admin_user and command.source == "api"

        status = api({"action": "calls.dial.status", "command_id": body["command_id"]}).json()
        assert status["success"] is True
        assert (
            status["command"]["status"] == "sent" and status["command"]["number"] == "+998901234567"
        )

    def test_most_recently_seen_online_device(
        self, company: Company, admin_user: User, operator: OperatorProfile, layer: FakeLayer
    ) -> None:
        enable_api_dial(company)
        go_online(operator, "older")
        go_online(operator, "newer")
        Device.all_objects.create(company=company, operator=operator, device_id="offline1")
        api({"action": "calls.dial", "operator": "op-1", "number": "+998901234567"})
        assert DialCommand.all_objects.get().device_id == "newer"

    def test_explicit_device_must_belong_to_operator(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        enable_api_dial(company)
        go_online(operator)
        response = api(
            {
                "action": "calls.dial",
                "operator": "op-1",
                "number": "+998901234567",
                "device_id": "nope",
            }
        )
        assert response.status_code == 404 and response.json()["error_code"] == "device_not_found"

    def test_operator_not_found_or_offline(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        enable_api_dial(company)
        missing = api({"action": "calls.dial", "operator": "ghost", "number": "+998901234567"})
        assert missing.status_code == 404 and missing.json()["error_code"] == "operator_not_found"
        no_device = api({"action": "calls.dial", "operator": "op-1", "number": "+998901234567"})
        assert no_device.status_code == 404
        Device.all_objects.create(company=company, operator=operator, device_id="phone0001")
        offline = api({"action": "calls.dial", "operator": "op-1", "number": "+998901234567"})
        assert offline.status_code == 409
        assert offline.json() == {
            "success": False,
            "error_code": "device_offline",
            "command_id": offline.json()["command_id"],
            "status": "offline",
        }

    @pytest.mark.parametrize(
        ("number", "code"),
        [("*100#", "invalid_number"), ("+447911123456", "destination_not_allowed")],
    )
    def test_number_validation(
        self, company: Company, admin_user: User, operator: OperatorProfile, number: str, code: str
    ) -> None:
        enable_api_dial(company)
        go_online(operator)
        response = api({"action": "calls.dial", "operator": "op-1", "number": number})
        assert response.status_code == 400 and response.json()["error_code"] == code

    def test_rate_limited(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        enable_api_dial(company)
        go_online(operator)
        body = {"action": "calls.dial", "operator": "op-1", "number": "+998901234567"}
        assert api(body).status_code == 200
        again = api(body)
        assert again.status_code == 429 and again.json()["error_code"] == "rate_limited"

    def test_status_is_company_scoped(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        enable_api_dial(company)
        other = Company.objects.create(name="O", slug="other-co", status=Company.Status.ACTIVE)
        foreign = DialCommand.all_objects.create(
            company=other, device_id="x", number="+998901234567"
        )
        response = api({"action": "calls.dial.status", "command_id": str(foreign.pk)})
        assert response.status_code == 404
        assert api({"action": "calls.dial.status", "command_id": "bad"}).status_code == 400

    def test_kotib_read_only_key_cannot_dial(
        self, company: Company, admin_user: User, operator: OperatorProfile
    ) -> None:
        enable_api_dial(company)
        CrmIntegration.all_objects.create(
            company=company,
            provider="kotib",
            is_enabled=True,
            config={"doocall_api_key": "k" * 32},
        )
        for action in ("calls.dial", "calls.dial.status"):
            response = APIClient().post(
                API,
                {"user_name": "admin@integr-co.uz", "api_key": "k" * 32, "action": action},
                format="json",
            )
            assert response.status_code == 403
        assert not DialCommand.all_objects.exists()


# ── Bitrix24 click-to-call ────────────────────────────────────────────────
@pytest.fixture
def bitrix(company: Company, operator: OperatorProfile) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={
            "webhook_url": HOOK,
            "user_id": "1",
            "user_map": {str(operator.pk): "21"},
            "click_to_call_enabled": True,
            "c2c_token": "tok-" + "c" * 40,
            "b24_app_token": "app-secret-token",
        },
    )


def event(**data: Any) -> dict[str, str]:
    body = {
        "event": "ONEXTERNALCALLSTART",
        "data[PHONE_NUMBER]": "901234567",
        "data[PHONE_NUMBER_INTERNATIONAL]": "+998901234567",
        "data[USER_ID]": "21",
        "data[CALL_ID]": "externalCall.abc123",
        "data[CRM_ENTITY_TYPE]": "CONTACT",
        "data[CRM_ENTITY_ID]": "77",
        "auth[application_token]": "app-secret-token",
        "auth[domain]": "acme.bitrix24.ru",
    }
    body.update(
        {k if k.startswith(("event", "auth[")) else f"data[{k}]": v for k, v in data.items()}
    )
    return body


def fire(bitrix: CrmIntegration, body: dict[str, str], token: str | None = None) -> Any:
    return APIClient().post(C2C + (token or bitrix.config["c2c_token"]), body)  # form-encoded


class TestClickToCall:
    def test_dials_the_mapped_operator(
        self, bitrix: CrmIntegration, operator: OperatorProfile, layer: FakeLayer
    ) -> None:
        go_online(operator)
        response = fire(bitrix, event())
        assert response.status_code == 200
        assert response.json()["status"] == "sent"
        frame = dial_frames(layer)[0]
        assert frame["number"] == "+998901234567" and frame["requested_by"] == "Bitrix24"
        command = DialCommand.all_objects.get()
        assert command.source == "bitrix24" and command.created_by is None
        assert command.b24_call_id == "externalCall.abc123" and command.b24_user_id == "21"
        assert (command.b24_entity_type, command.b24_entity_id) == ("CONTACT", "77")
        assert command.operator_id == operator.pk

    def test_resent_event_dials_once(
        self, bitrix: CrmIntegration, operator: OperatorProfile, layer: FakeLayer
    ) -> None:
        go_online(operator)
        fire(bitrix, event())
        again = fire(bitrix, event())
        assert again.json()["status"] == "duplicate"
        assert DialCommand.all_objects.count() == 1 and len(dial_frames(layer)) == 1

    def test_unknown_token_404(self, bitrix: CrmIntegration) -> None:
        assert fire(bitrix, event(), token="nope").status_code == 404

    @pytest.mark.parametrize("app_token", ["", "wrong"])
    def test_application_token_required(
        self, bitrix: CrmIntegration, operator: OperatorProfile, app_token: str
    ) -> None:
        go_online(operator)
        body = event()
        body["auth[application_token]"] = app_token
        assert fire(bitrix, body).status_code == 401
        assert not DialCommand.all_objects.exists()

    def test_no_app_token_configured_accepts(
        self, bitrix: CrmIntegration, operator: OperatorProfile
    ) -> None:
        bitrix.config = {k: v for k, v in bitrix.config.items() if k != "b24_app_token"}
        bitrix.save()
        go_online(operator)
        body = event()
        body.pop("auth[application_token]")
        assert fire(bitrix, body).json()["status"] == "sent"

    def test_disabled_or_other_event_ignored(
        self, bitrix: CrmIntegration, operator: OperatorProfile
    ) -> None:
        go_online(operator)
        other = event()
        other["event"] = "ONEXTERNALCALLBACKSTART"
        assert fire(bitrix, other).json()["status"] == "ignored"
        bitrix.config = {**bitrix.config, "click_to_call_enabled": False}
        bitrix.save()
        assert fire(bitrix, event()).json() == {
            "success": True,
            "status": "ignored",
            "reason": "disabled",
        }
        assert not DialCommand.all_objects.exists()

    def test_unmapped_user_ignored(
        self, bitrix: CrmIntegration, operator: OperatorProfile, caplog: pytest.LogCaptureFixture
    ) -> None:
        go_online(operator)
        response = fire(bitrix, event(USER_ID="999"))
        assert response.status_code == 200 and response.json()["reason"] == "unmapped_user"
        assert "ignored=unmapped_user" in caplog.text
        assert not DialCommand.all_objects.exists()

    def test_offline_and_invalid_number(
        self, bitrix: CrmIntegration, operator: OperatorProfile
    ) -> None:
        Device.all_objects.create(
            company=operator.company, operator=operator, device_id="phone0001"
        )
        offline = fire(bitrix, event())
        assert offline.status_code == 200 and offline.json()["status"] == "offline"
        refused = fire(
            bitrix, event(CALL_ID="c2", PHONE_NUMBER="*100#", PHONE_NUMBER_INTERNATIONAL="")
        )
        assert refused.json() == {
            "success": True,
            "status": "refused",
            "error_code": "invalid_number",
        }

    def test_json_body_is_accepted(self, bitrix: CrmIntegration, operator: OperatorProfile) -> None:
        go_online(operator)
        body = {
            "event": "ONEXTERNALCALLSTART",
            "data": {"PHONE_NUMBER": "+998901234567", "USER_ID": "21", "CALL_ID": "j1"},
            "auth": {"application_token": "app-secret-token"},
        }
        response = APIClient().post(
            C2C + bitrix.config["c2c_token"], json.dumps(body), content_type="application/json"
        )
        assert response.json()["status"] == "sent"


class FakeBitrix:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail = fail or set()

    def __call__(self, url: str, payload: Any = None, **_: Any) -> Any:
        method = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.calls.append((method, payload))
        if method in self.fail:
            return {"error": "ERROR_CORE", "error_description": f"{method} failed"}
        if method == "telephony.externalcall.register":
            return {"result": {"CALL_ID": "NEW1", "CRM_ENTITY_TYPE": "LEAD", "CRM_ENTITY_ID": 5}}
        if method == "telephony.externalLine.add":
            return {"result": {"ID": 7}}
        if method == "crm.settings.mode.get":
            return {"result": 1}
        if method == "telephony.externalcall.searchCrmEntities":
            return {"result": []}
        return {"result": True}

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


@pytest.fixture
def outbound(call: CallRecord, operator: OperatorProfile) -> CallRecord:
    call.call_type = CallRecord.CallType.OUTBOUND
    call.counterparty_number = "+998901234567"
    call.save(update_fields=["call_type", "counterparty_number"])
    call.audios.all().delete()
    return call


def _c2c_command(op: OperatorProfile, call: CallRecord, **extra: Any) -> DialCommand:
    command = DialCommand.all_objects.create(
        company=op.company,
        operator=op,
        device_id="phone0001",
        number="+998901234567",
        source="bitrix24",
        b24_call_id="externalCall.abc123",
        b24_user_id="21",
        b24_entity_type="CONTACT",
        b24_entity_id="77",
        **extra,
    )
    DialCommand.all_objects.filter(pk=command.pk).update(
        created_at=call.start_time - timedelta(minutes=1)
    )
    return command


class TestCallIdReuse:
    def test_delivery_finishes_the_bitrix_call(
        self,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        outbound: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        command = _c2c_command(operator, outbound)
        fake = FakeBitrix()
        monkeypatch.setattr(providers, "_http_json", fake)
        assert tasks.dispatch_call(outbound.pk) == 1
        assert "telephony.externalcall.register" not in fake.methods()
        finish = next(p for m, p in fake.calls if m == "telephony.externalcall.finish")
        assert finish["CALL_ID"] == "externalCall.abc123" and finish["USER_ID"] == 21
        assert finish["DURATION"] == outbound.duration
        command.refresh_from_db()
        assert command.b24_used_at is not None
        assert CrmDelivery.all_objects.get(call=outbound).external_id == "externalCall.abc123"

    def test_used_or_stale_or_other_number_registers_normally(
        self,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        outbound: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _c2c_command(operator, outbound, b24_used_at=timezone.now())  # already consumed
        stale = _c2c_command(operator, outbound)
        DialCommand.all_objects.filter(pk=stale.pk).update(
            created_at=outbound.start_time - timedelta(minutes=30)
        )
        other = _c2c_command(operator, outbound)
        DialCommand.all_objects.filter(pk=other.pk).update(number="+998909999999")
        fake = FakeBitrix()
        monkeypatch.setattr(providers, "_http_json", fake)
        tasks.dispatch_call(outbound.pk)
        assert "telephony.externalcall.register" in fake.methods()

    def test_inbound_calls_never_reuse(
        self,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        outbound: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _c2c_command(operator, outbound)
        CallRecord.all_objects.filter(pk=outbound.pk).update(call_type=CallRecord.CallType.INBOUND)
        fake = FakeBitrix()
        monkeypatch.setattr(providers, "_http_json", fake)
        tasks.dispatch_call(outbound.pk)
        assert "telephony.externalcall.register" in fake.methods()

    def test_finish_failure_releases_the_claim(
        self,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        outbound: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        command = _c2c_command(operator, outbound)
        monkeypatch.setattr(
            providers, "_http_json", FakeBitrix(fail={"telephony.externalcall.finish"})
        )
        tasks.dispatch_call(outbound.pk)
        command.refresh_from_db()
        assert command.b24_used_at is None  # a retry can still finish that call
        assert CrmDelivery.all_objects.get(call=outbound).status == "error"


class TestClickToCallSettings:
    URL = "/api/web/v1/settings/integrations/bitrix24"

    def _card(self, client: APIClient) -> dict[str, Any]:
        rows = client.get("/api/web/v1/settings/integrations").json()["integrations"]
        return next(r for r in rows if r["provider"] == "bitrix24")["config"]

    def test_enable_creates_token_and_line(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeBitrix()
        monkeypatch.setattr(providers, "_http_json", fake)
        response = client.put(
            self.URL,
            {
                "is_enabled": True,
                "config": {
                    "webhook_url": HOOK,
                    "click_to_call_enabled": True,
                    "b24_app_token": "app-secret-token",
                },
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        add = next(p for m, p in fake.calls if m == "telephony.externalLine.add")
        assert add["NUMBER"] == "DooCall" and add["CRM_AUTO_CREATE"] == "N"
        card = self._card(client)
        row = CrmIntegration.all_objects.get(company=company, provider="bitrix24")
        assert card["click_to_call_enabled"] is True
        assert card["click_to_call_url"].endswith(
            f"/api/public/bitrix24/click-to-call/{row.config['c2c_token']}"
        )
        assert card["click_to_call_url"].split("://")[1].startswith("integr-co.")
        assert card["b24_app_token_set"] is True and "app-secret-token" not in json.dumps(card)
        assert card["external_line_registered"] is True
        # Re-save keeps the token, doesn't add the line twice.
        token = row.config["c2c_token"]
        client.put(self.URL, {"is_enabled": True, "config": {"lead_source": "WEB"}}, format="json")
        row.refresh_from_db()
        assert row.config["c2c_token"] == token
        assert fake.methods().count("telephony.externalLine.add") == 1

    def test_line_failure_is_best_effort(
        self, client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            providers, "_http_json", FakeBitrix(fail={"telephony.externalLine.add"})
        )
        response = client.put(
            self.URL,
            {"is_enabled": True, "config": {"webhook_url": HOOK, "click_to_call_enabled": True}},
            format="json",
        )
        assert response.status_code == 200
        card = self._card(client)
        assert card["external_line_registered"] is False and card["click_to_call_url"]

    def test_disabled_shows_no_url(self, client: APIClient, company: Company) -> None:
        card = self._card(client)
        assert card["click_to_call_enabled"] is False and card["click_to_call_url"] == ""
        assert card["b24_app_token_set"] is False
