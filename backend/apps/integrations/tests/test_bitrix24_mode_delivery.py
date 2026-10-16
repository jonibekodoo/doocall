"""Bitrix24 CRM-mode cache from the DELIVERY path (prod: CDTI's mode was only
set by an admin re-save) + one structured log line per call with its branch."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmDelivery, CrmIntegration

from .test_bitrix24_cards import HOOK, MODE, REGISTER, Bitrix

pytestmark = pytest.mark.django_db


@pytest.fixture
def b24(monkeypatch: pytest.MonkeyPatch) -> Bitrix:
    fake = Bitrix()
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


@pytest.fixture
def quiet_call(call: CallRecord) -> CallRecord:
    call.audios.all().delete()
    return call


def _integration(company: Company, **config: Any) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": HOOK, **config},
    )


def _branches(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage().split("branch=")[1].split()[0]
        for r in caplog.records
        if r.getMessage().startswith("bitrix24 delivery ")
    ]


class TestModeCacheFromDelivery:
    def test_unknown_number_empty_cache_is_persisted(
        self, company: Company, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        integration = _integration(company)
        b24.mode = 2
        assert tasks.dispatch_call(quiet_call.pk) == 1
        integration.refresh_from_db()
        assert integration.config["crm_mode"] == "simple"
        assert integration.config["crm_mode_checked_at"]
        assert integration.config["crm_mode_assumed"] is False

    def test_known_number_empty_cache_is_persisted(
        self, company: Company, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        """CDTI case: every call was to an existing contact — the mode must
        still be detected (and cached) by the first delivery."""
        integration = _integration(company)
        b24.crm["+998901112233"] = [{"CRM_ENTITY_TYPE": "CONTACT", "CRM_ENTITY_ID": 5}]
        assert tasks.dispatch_call(quiet_call.pk) == 1
        integration.refresh_from_db()
        assert integration.config["crm_mode"] == "classic"
        assert integration.config["crm_mode_checked_at"]
        # Second delivery uses the cache (no new mode request).
        tasks.dispatch_call(quiet_call.pk)
        assert [m for m, _ in b24.calls].count(MODE) == 1

    def test_explicit_contact_mode_does_not_need_the_mode(
        self, company: Company, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        _integration(company, create_card="contact")
        tasks.dispatch_call(quiet_call.pk)
        assert MODE not in [m for m, _ in b24.calls]


class TestBranchLog:
    @pytest.mark.parametrize(
        ("config", "mode", "known", "status", "branch"),
        [
            ({}, 1, True, "answered", "existing_entity"),
            ({}, 1, False, "answered", "created_lead"),
            ({}, 2, False, "answered", "created_contact_deal"),
            ({"create_card": "contact"}, 1, False, "answered", "created_contact"),
            ({"create_card": "lead"}, 2, False, "answered", "created_contact"),
            ({"create_card": "none"}, 1, False, "answered", "no_card"),
            ({"save_external_calls": False}, 1, False, "answered", "skipped_unknown"),
            ({"only_answered": True}, 1, False, "no_answer", "skipped_unanswered"),
        ],
    )
    def test_one_structured_line_per_delivery(
        self,
        company: Company,
        b24: Bitrix,
        quiet_call: CallRecord,
        caplog: pytest.LogCaptureFixture,
        config: dict[str, Any],
        mode: int,
        known: bool,
        status: str,
        branch: str,
    ) -> None:
        _integration(company, **config)
        b24.mode = mode
        if known:
            b24.crm["+998901112233"] = [{"CRM_ENTITY_TYPE": "LEAD", "CRM_ENTITY_ID": 3}]
        quiet_call.call_status = status
        quiet_call.save(update_fields=["call_status"])
        with caplog.at_level(logging.INFO, logger="apps.integrations.providers"):
            tasks.dispatch_call(quiet_call.pk)
        assert _branches(caplog) == [branch]
        line = next(r.getMessage() for r in caplog.records if "branch=" in r.getMessage())
        assert f"company={company.pk}" in line and f"call={quiet_call.pk}" in line
        assert "crm_mode=" in line
        # No phone numbers or URLs in the line.
        assert "998901112233" not in line and "http" not in line
        assert CrmDelivery.all_objects.filter(call=quiet_call).count() == 1

    def test_register_payload_unchanged_for_known_numbers(
        self, company: Company, b24: Bitrix, quiet_call: CallRecord
    ) -> None:
        _integration(company)
        b24.crm["+998901112233"] = [{"CRM_ENTITY_TYPE": "CONTACT", "CRM_ENTITY_ID": 5}]
        tasks.dispatch_call(quiet_call.pk)
        register = b24.payload(REGISTER)
        assert register["CRM_CREATE"] == 0 and register["CRM_ENTITY_ID"] == 5
