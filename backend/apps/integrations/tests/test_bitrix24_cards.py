"""Bitrix24 moizvonki-style options: save calls made outside Bitrix24 and
create a CRM card (lead / contact / deal / none) for unknown numbers."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmDelivery, CrmIntegration

pytestmark = pytest.mark.django_db

HOOK = "https://acme.bitrix24.ru/rest/1/tok/"
SEARCH = "telephony.externalcall.searchCrmEntities"
REGISTER = "telephony.externalcall.register"
FINISH = "telephony.externalcall.finish"
MODE = "crm.settings.mode.get"


class Bitrix:
    """Fake Bitrix24 REST: a tiny CRM keyed by phone, so retries see what an
    earlier attempt created. ``fail`` makes one method raise once."""

    def __init__(self, known: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.crm = known or {}
        self.calls: list[tuple[str, Any]] = []
        self.fail: dict[str, int] = {}
        self.next_id = 100
        self.mode: Any = 1  # crm.settings.mode.get: 1 classic, 2 simple

    def __call__(self, url: str, payload: Any = None, **_: Any) -> Any:
        method = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.calls.append((method, payload))
        if self.fail.get(method):
            self.fail[method] -= 1
            return {"error": "ERROR_CORE", "error_description": f"{method} failed"}
        if method == MODE:
            return {"result": self.mode}
        if method == "profile":
            return {"result": {"ID": "1", "NAME": "Admin"}}
        if method == SEARCH:
            return {"result": self.crm.get(payload["PHONE_NUMBER"], [])}
        if method in ("crm.contact.add", "crm.deal.add"):
            self.next_id += 1
            if method == "crm.contact.add":
                phone = payload["fields"]["PHONE"][0]["VALUE"]
                self.crm.setdefault(phone, []).append(
                    {"CRM_ENTITY_TYPE": "CONTACT", "CRM_ENTITY_ID": self.next_id}
                )
            return {"result": self.next_id}
        if method == REGISTER:
            return {
                "result": {
                    "CALL_ID": "EC1",
                    "CRM_ENTITY_TYPE": payload.get("CRM_ENTITY_TYPE", "LEAD"),
                    "CRM_ENTITY_ID": payload.get("CRM_ENTITY_ID", 42),
                }
            }
        return {"result": True}

    def methods(self) -> list[str]:
        """Calls except the (cached) portal-mode lookup."""
        return [m for m, _ in self.calls if m != MODE]

    def payload(self, method: str) -> Any:
        return next(p for m, p in self.calls if m == method)


@pytest.fixture
def b24(monkeypatch: pytest.MonkeyPatch) -> Bitrix:
    fake = Bitrix()
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


@pytest.fixture
def quiet_call(call: CallRecord) -> CallRecord:
    call.audios.all().delete()  # no recording → no attach step
    return call


def _send(call: CallRecord, **options: Any) -> None:
    providers.send_call("bitrix24", {"webhook_url": HOOK, "user_id": "7", **options}, call, None)


class TestUnknownNumber:
    def test_default_is_lead_created_by_bitrix(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        _send(quiet_call)
        assert b24.methods() == [SEARCH, REGISTER, FINISH]
        assert b24.payload(SEARCH) == {"PHONE_NUMBER": "+998901112233"}
        register = b24.payload(REGISTER)
        assert register["CRM_CREATE"] == 1 and register["CRM_SOURCE"] == "CALL"
        assert "CRM_ENTITY_ID" not in register

    def test_lead_uses_configured_source(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        _send(quiet_call, lead_source="UC_DOOCALL")
        assert b24.payload(REGISTER)["CRM_SOURCE"] == "UC_DOOCALL"

    def test_contact_mode(
        self, b24: Bitrix, quiet_call: CallRecord, operator: OperatorProfile
    ) -> None:
        quiet_call.resolved_name = "Aziz Karimov"
        quiet_call.save(update_fields=["resolved_name"])
        _send(quiet_call, create_card="contact", user_map={str(operator.pk): "21"})
        assert b24.methods() == [SEARCH, "crm.contact.add", REGISTER, FINISH]
        fields = b24.payload("crm.contact.add")["fields"]
        assert fields["NAME"] == "Aziz Karimov"
        assert fields["PHONE"] == [{"VALUE": "+998901112233", "VALUE_TYPE": "WORK"}]
        assert fields["ASSIGNED_BY_ID"] == 21 and fields["SOURCE_ID"] == "CALL"
        register = b24.payload(REGISTER)
        assert register["CRM_CREATE"] == 0
        assert register["CRM_ENTITY_TYPE"] == "CONTACT" and register["CRM_ENTITY_ID"] == 101
        assert register["USER_ID"] == 21

    def test_contact_name_falls_back_to_phone(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        _send(quiet_call, create_card="contact")
        assert b24.payload("crm.contact.add")["fields"]["NAME"] == "+998901112233"
        assert b24.payload("crm.contact.add")["fields"]["ASSIGNED_BY_ID"] == 7

    def test_deal_mode(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        _send(quiet_call, create_card="deal", lead_source="WEB")
        assert b24.methods() == [SEARCH, "crm.contact.add", "crm.deal.add", REGISTER, FINISH]
        deal = b24.payload("crm.deal.add")["fields"]
        assert deal == {
            "TITLE": "DooCall: +998901112233",
            "CONTACT_ID": 101,
            "ASSIGNED_BY_ID": 7,
            "SOURCE_ID": "WEB",
        }
        register = b24.payload(REGISTER)
        assert register["CRM_ENTITY_TYPE"] == "CONTACT" and register["CRM_ENTITY_ID"] == 101

    def test_none_mode_saves_call_without_card(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        _send(quiet_call, create_card="none")
        assert b24.methods() == [SEARCH, REGISTER, FINISH]
        assert b24.payload(REGISTER)["CRM_CREATE"] == 0

    def test_save_external_calls_off_skips(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        with pytest.raises(providers.CallSkipped):
            _send(quiet_call, save_external_calls=False, create_card="contact")
        assert b24.methods() == [SEARCH]  # nothing registered, no card


class TestKnownNumber:
    @pytest.mark.parametrize("mode", ["lead", "contact", "deal", "none"])
    def test_existing_entity_is_bound_never_duplicated(
        self, b24: Bitrix, quiet_call: CallRecord, mode: str
    ) -> None:
        b24.crm["+998901112233"] = [{"CRM_ENTITY_TYPE": "COMPANY", "CRM_ENTITY_ID": 9}]
        _send(quiet_call, create_card=mode)
        assert b24.methods() == [SEARCH, REGISTER, FINISH]
        register = b24.payload(REGISTER)
        assert register["CRM_CREATE"] == 0
        assert register["CRM_ENTITY_TYPE"] == "COMPANY" and register["CRM_ENTITY_ID"] == 9

    def test_known_number_is_sent_even_when_external_off(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        b24.crm["+998901112233"] = [{"CRM_ENTITY_TYPE": "LEAD", "CRM_ENTITY_ID": 5}]
        _send(quiet_call, save_external_calls=False)
        assert REGISTER in b24.methods()


class TestOnlyAnswered:
    def test_missed_call_skipped_without_any_request(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        quiet_call.call_status = CallRecord.CallStatus.NO_ANSWER
        quiet_call.save(update_fields=["call_status"])
        with pytest.raises(providers.CallSkipped):
            _send(quiet_call, only_answered=True)
        assert b24.calls == []

    def test_missed_call_sent_by_default(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        quiet_call.call_status = CallRecord.CallStatus.NO_ANSWER
        quiet_call.save(update_fields=["call_status"])
        _send(quiet_call)
        assert b24.payload(FINISH)["STATUS_CODE"] == 304


class TestRetry:
    def test_retry_after_failure_reuses_created_contact(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        b24.fail[REGISTER] = 1
        with pytest.raises(providers.ProviderError):
            _send(quiet_call, create_card="contact")
        _send(quiet_call, create_card="contact")  # retry
        assert b24.methods().count("crm.contact.add") == 1
        registers = [p for m, p in b24.calls if m == REGISTER]
        assert registers[-1]["CRM_ENTITY_ID"] == 101
        assert all(p["EXTERNAL_CALL_ID"] == quiet_call.server_id.hex for p in registers)

    def test_deal_retry_creates_no_second_contact_or_deal(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        _send(quiet_call, create_card="deal")
        _send(quiet_call, create_card="deal")  # e.g. manual retry
        assert b24.methods().count("crm.contact.add") == 1
        assert b24.methods().count("crm.deal.add") == 1


class TestDispatch:
    @pytest.fixture
    def bitrix(self, company: Company) -> CrmIntegration:
        return CrmIntegration.all_objects.create(
            company=company,
            provider="bitrix24",
            is_enabled=True,
            config={"webhook_url": HOOK, "save_external_calls": False},
        )

    def test_skip_is_recorded_as_ok_note_and_keeps_health(
        self, bitrix: CrmIntegration, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        bitrix.last_status, bitrix.last_error = "error", "HTTP 500"
        bitrix.save()
        assert tasks.dispatch_call(quiet_call.pk) == 1
        delivery = CrmDelivery.all_objects.get(call=quiet_call)
        assert delivery.status == "ok" and delivery.error.startswith("skipped:")
        bitrix.refresh_from_db()
        assert bitrix.last_status == "ok" and bitrix.last_error == ""


URL = "/api/web/v1/settings/integrations/bitrix24"


class TestConfig:
    def _card(self, client: APIClient) -> dict[str, Any]:
        rows = client.get("/api/web/v1/settings/integrations").json()["integrations"]
        return next(r for r in rows if r["provider"] == "bitrix24")["config"]

    def test_defaults_shown_for_new_and_old_rows(self, client: APIClient, company: Company) -> None:
        defaults = {
            "save_external_calls": True,
            "create_card": "auto",
            "lead_source": "CALL",
            "only_answered": False,
            "crm_mode": "",
            "crm_mode_assumed": False,
        }
        assert {k: self._card(client)[k] for k in defaults} == defaults
        CrmIntegration.all_objects.create(
            company=company, provider="bitrix24", config={"webhook_url": HOOK}
        )
        assert {k: self._card(client)[k] for k in defaults} == defaults

    def test_save_valid_options(self, client: APIClient, company: Company) -> None:
        response = client.put(
            URL,
            {
                "config": {
                    "webhook_url": HOOK,
                    "save_external_calls": "false",
                    "create_card": "Deal",
                    "lead_source": "uc_abc1",
                    "only_answered": 1,
                }
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        row = CrmIntegration.all_objects.get(company=company, provider="bitrix24")
        assert row.config["save_external_calls"] is False
        assert row.config["create_card"] == "deal"
        assert row.config["lead_source"] == "UC_ABC1"
        assert row.config["only_answered"] is True
        card = response.json()["integration"]["config"]
        assert card["create_card"] == "deal" and card["only_answered"] is True

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("create_card", "company"),
            ("create_card", 5),
            ("save_external_calls", "maybe"),
            ("only_answered", {"x": 1}),
            ("only_answered", [True]),
            ("lead_source", "CALL; DROP"),
            ("lead_source", "Ё"),
            ("lead_source", "X" * 51),
        ],
    )
    def test_invalid_options_rejected(
        self, client: APIClient, company: Company, field: str, value: Any
    ) -> None:
        response = client.put(URL, {"config": {"webhook_url": HOOK, field: value}}, format="json")
        assert response.status_code == 400
        assert field in response.json()["message"]
        assert not CrmIntegration.all_objects.filter(company=company).exists()


class TestAutoMode:
    """create_card="auto" (default): leads only on classic portals; portals
    without leads (simple CRM) get contact + deal, never a lead."""

    def _config(self, **extra: Any) -> dict[str, Any]:
        return {"webhook_url": HOOK, "user_id": "7", **extra}

    def test_classic_portal_gets_lead(self, b24: Bitrix, quiet_call: CallRecord) -> None:
        config = self._config()
        assert providers.send_call("bitrix24", config, quiet_call, None) is None
        assert b24.payload(REGISTER)["CRM_CREATE"] == 1
        assert config["crm_mode"] == "classic" and config["crm_mode_assumed"] is False

    def test_simple_portal_gets_contact_and_deal(
        self, b24: Bitrix, quiet_call: CallRecord, operator: OperatorProfile
    ) -> None:
        b24.mode = 2
        config = self._config(user_map={str(operator.pk): "21"})
        assert providers.send_call("bitrix24", config, quiet_call, None) is None
        assert b24.methods() == [SEARCH, "crm.contact.add", "crm.deal.add", REGISTER, FINISH]
        register = b24.payload(REGISTER)
        assert register["CRM_CREATE"] == 0 and register["CRM_ENTITY_TYPE"] == "CONTACT"
        assert "CRM_SOURCE" not in register
        assert b24.payload("crm.deal.add")["fields"]["ASSIGNED_BY_ID"] == 21
        assert config["crm_mode"] == "simple"

    def test_explicit_lead_on_simple_portal_becomes_contact_with_note(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        b24.mode = 2
        note = providers.send_call("bitrix24", self._config(create_card="lead"), quiet_call, None)
        assert note == providers.B24_LEAD_FALLBACK_NOTE
        assert b24.methods() == [SEARCH, "crm.contact.add", REGISTER, FINISH]
        assert b24.payload(REGISTER)["CRM_CREATE"] == 0

    @pytest.mark.parametrize("answer", ["fail", "garbage"])
    def test_detection_failure_assumes_simple(
        self,
        b24: Bitrix,
        quiet_call: CallRecord,
        caplog: pytest.LogCaptureFixture,
        answer: str,
    ) -> None:
        if answer == "fail":
            b24.fail[MODE] = 1  # e.g. webhook without the crm scope
        else:
            b24.mode = "x"
        config = self._config()
        providers.send_call("bitrix24", config, quiet_call, None)
        assert config["crm_mode"] == "simple" and config["crm_mode_assumed"] is True
        assert b24.payload(REGISTER)["CRM_CREATE"] == 0  # no lead
        assert "assuming simple CRM" in caplog.text

    def test_mode_is_cached_and_refreshed_after_24h(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        from datetime import timedelta

        from django.utils import timezone

        config = self._config()
        providers.send_call("bitrix24", config, quiet_call, None)
        providers.send_call("bitrix24", config, quiet_call, None)
        assert [m for m, _ in b24.calls].count(MODE) == 1  # cached

        old = timezone.now() - timedelta(hours=25)
        config["crm_mode_checked_at"] = old.isoformat()
        b24.mode = 2  # portal switched leads off meanwhile
        providers.send_call("bitrix24", config, quiet_call, None)
        assert [m for m, _ in b24.calls].count(MODE) == 2
        assert config["crm_mode"] == "simple"

    def test_assumed_mode_is_retried_after_an_hour(
        self, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        from datetime import timedelta

        from django.utils import timezone

        two_hours_ago = (timezone.now() - timedelta(hours=2)).isoformat()
        config = self._config(
            crm_mode="simple", crm_mode_assumed=True, crm_mode_checked_at=two_hours_ago
        )
        providers.send_call("bitrix24", config, quiet_call, None)
        assert config["crm_mode"] == "classic" and config["crm_mode_assumed"] is False

    def test_dispatch_persists_mode_and_shows_note(
        self, company: Company, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        b24.mode = 2
        integration = CrmIntegration.all_objects.create(
            company=company,
            provider="bitrix24",
            is_enabled=True,
            config={"webhook_url": HOOK, "create_card": "lead"},
        )
        assert tasks.dispatch_call(quiet_call.pk) == 1
        integration.refresh_from_db()
        assert integration.config["crm_mode"] == "simple"
        assert integration.last_status == "ok"
        assert integration.last_error == providers.B24_LEAD_FALLBACK_NOTE
        delivery = CrmDelivery.all_objects.get(call=quiet_call)
        assert delivery.status == "ok" and delivery.error == providers.B24_LEAD_FALLBACK_NOTE

    def test_save_and_test_refresh_mode_and_get_shows_it(
        self, client: APIClient, company: Company, b24: Bitrix
    ) -> None:
        b24.mode = 2
        response = client.put(
            URL, {"is_enabled": True, "config": {"webhook_url": HOOK}}, format="json"
        )
        assert response.status_code == 200
        card = response.json()["integration"]["config"]
        assert card["crm_mode"] == "simple" and card["crm_mode_assumed"] is False
        assert card["crm_mode_checked_at"]

        b24.mode = 1
        assert client.post(f"{URL}/test").status_code == 200
        rows = client.get("/api/web/v1/settings/integrations").json()["integrations"]
        assert (
            next(r for r in rows if r["provider"] == "bitrix24")["config"]["crm_mode"] == "classic"
        )
