"""Bitrix24 CALL_ID stored on delivery + attaching a late recording to it."""

from __future__ import annotations

import base64
import logging
from typing import Any

import pytest

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core import audio as audio_tools
from apps.integrations import providers, tasks
from apps.integrations.models import CrmDelivery, CrmIntegration

from .test_bitrix24_cards import HOOK, Bitrix

pytestmark = pytest.mark.django_db

ATTACH = "telephony.externalcall.attachrecord"


@pytest.fixture
def b24(monkeypatch: pytest.MonkeyPatch) -> Bitrix:
    fake = Bitrix()
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


@pytest.fixture
def bitrix(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": HOOK, "create_card": "none"},
    )


def _audio_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers, "_read_audio", lambda key: b"OggS-late")
    monkeypatch.setattr(audio_tools, "playable", lambda data, ext="": (b"ID3-late", "mp3"))


def _late_log(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("late audio ")]


class TestExternalId:
    def test_successful_delivery_stores_call_id(
        self, bitrix: CrmIntegration, b24: Bitrix, call: CallRecord
    ) -> None:
        call.audios.all().delete()
        tasks.dispatch_call(call.pk)
        delivery = CrmDelivery.all_objects.get(call=call)
        assert delivery.status == "ok" and delivery.external_id == "EC1"
        bitrix.refresh_from_db()
        assert providers.DELIVERY_EXTERNAL_ID not in bitrix.config  # never persisted

    def test_failed_delivery_has_no_external_id(
        self, bitrix: CrmIntegration, b24: Bitrix, call: CallRecord
    ) -> None:
        b24.fail["telephony.externalcall.finish"] = 1  # register ok, finish fails
        tasks.dispatch_call(call.pk)
        delivery = CrmDelivery.all_objects.get(call=call)
        assert delivery.status == "error" and delivery.external_id == ""

    def test_other_providers_leave_it_blank(
        self, company: Company, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        CrmIntegration.all_objects.create(
            company=company,
            provider="amocrm",
            is_enabled=True,
            config={"base_url": "https://acme.amocrm.ru", "access_token": "t" * 20},
        )
        monkeypatch.setattr(providers, "send_call", lambda *a: None)
        tasks.dispatch_call(call.pk)
        assert CrmDelivery.all_objects.get(call=call).external_id == ""


def _delivered(call: CallRecord, external_id: str = "EC9", **extra: Any) -> CrmDelivery:
    return CrmDelivery.all_objects.create(
        company=call.company,
        call=call,
        provider="bitrix24",
        status=extra.pop("status", "ok"),
        external_id=external_id,
        **extra,
    )


class TestLateAttach:
    def test_attaches_to_stored_call_id(
        self,
        bitrix: CrmIntegration,
        b24: Bitrix,
        call: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _delivered(call, "EC-old")
        _delivered(call, "EC9")  # latest OK delivery wins
        _audio_ok(monkeypatch)
        with caplog.at_level(logging.INFO, logger="apps.integrations.tasks"):
            assert tasks.attach_late_audio(call.pk) == "attached"
        attach = b24.payload(ATTACH)
        assert attach["CALL_ID"] == "EC9"
        assert attach["FILENAME"] == f"doocall-{call.server_id.hex}.mp3"
        assert base64.b64decode(attach["FILE_CONTENT"]) == b"ID3-late"
        assert _late_log(caplog) == [
            f"late audio company={call.company_id} call={call.pk} bitrix24=attached"
        ]

    def test_failed_or_blank_deliveries_are_skipped(
        self,
        bitrix: CrmIntegration,
        b24: Bitrix,
        call: CallRecord,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _delivered(call, "")  # delivered before CALL_IDs were stored
        _delivered(call, "EC5", status="error")
        with caplog.at_level(logging.INFO, logger="apps.integrations.tasks"):
            assert tasks.attach_late_audio(call.pk) == "skipped"
        assert b24.calls == []
        assert _late_log(caplog)[0].endswith("bitrix24=skipped")

    def test_attach_failure_is_error(
        self,
        bitrix: CrmIntegration,
        b24: Bitrix,
        call: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _delivered(call)
        monkeypatch.setattr(providers, "_read_audio", lambda key: b"x")

        def broken(data: bytes, ext: str = "") -> Any:
            raise audio_tools.AudioError("transcode failed")

        monkeypatch.setattr(audio_tools, "playable", broken)
        assert tasks.attach_late_audio(call.pk) == "error"  # .ogg: no URL/comment target

    def test_unexpected_exception_is_error(
        self,
        bitrix: CrmIntegration,
        call: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _delivered(call)

        def boom(*args: Any) -> Any:
            raise RuntimeError("boom")

        monkeypatch.setattr(providers, "_b24_attach_recording", boom)
        assert tasks.attach_late_audio(call.pk) == "error"

    def test_no_bitrix_integration_or_disabled(
        self, company: Company, call: CallRecord, b24: Bitrix
    ) -> None:
        _delivered(call)
        assert tasks.attach_late_audio(call.pk) == "skipped"
        CrmIntegration.all_objects.create(
            company=company, provider="bitrix24", is_enabled=False, config={"webhook_url": HOOK}
        )
        assert tasks.attach_late_audio(call.pk) == "skipped"
        assert b24.calls == []

    def test_unknown_call(self) -> None:
        assert tasks.attach_late_audio(999999) == "skipped"
