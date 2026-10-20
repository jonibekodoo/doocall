"""Bitrix24 register carries the operator's SIM number as LINE_NUMBER, so
the timeline shows "С номера +998…" instead of "REST_APP:"."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmIntegration

from .test_bitrix24_cards import FINISH, HOOK, REGISTER, Bitrix

pytestmark = pytest.mark.django_db


@pytest.fixture
def b24(monkeypatch: pytest.MonkeyPatch) -> Bitrix:
    fake = Bitrix()
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


@pytest.fixture
def sim_call(call: CallRecord) -> CallRecord:
    call.audios.all().delete()
    call.operator_number = "+998998887766"
    call.save(update_fields=["operator_number"])
    return call


def _send(call: CallRecord, **config: Any) -> None:
    providers.send_call(
        "bitrix24",
        {"webhook_url": HOOK, "user_id": "7", "create_card": "none", **config},
        call,
        None,
    )


def _registers(b24: Bitrix) -> list[dict[str, Any]]:
    return [p for m, p in b24.calls if m == REGISTER]


def test_operator_number_is_sent_as_line_number(b24: Bitrix, sim_call: CallRecord) -> None:
    _send(sim_call)
    assert _registers(b24)[0]["LINE_NUMBER"] == "+998998887766"
    assert _registers(b24)[0]["PHONE_NUMBER"] == "+998901112233"  # counterparty unchanged


@pytest.mark.parametrize("number", [None, "", "   "])
def test_empty_operator_number_omits_line_number(
    b24: Bitrix, sim_call: CallRecord, number: str | None
) -> None:
    sim_call.operator_number = number
    sim_call.save(update_fields=["operator_number"])
    _send(sim_call)
    assert "LINE_NUMBER" not in _registers(b24)[0]


def test_rejected_line_retries_once_without_it(
    b24: Bitrix, sim_call: CallRecord, caplog: pytest.LogCaptureFixture
) -> None:
    b24.fail[REGISTER] = 1
    with caplog.at_level(logging.WARNING, logger="apps.integrations.providers"):
        _send(sim_call)
    registers = _registers(b24)
    assert len(registers) == 2
    assert registers[0]["LINE_NUMBER"] == "+998998887766"
    assert "LINE_NUMBER" not in registers[1]
    assert FINISH in b24.methods()
    assert "retrying without it" in caplog.text
    assert "998998887766" not in caplog.text  # no phone numbers in the log


def test_both_attempts_failing_raises(b24: Bitrix, sim_call: CallRecord) -> None:
    b24.fail[REGISTER] = 2
    with pytest.raises(providers.ProviderError):
        _send(sim_call)
    assert len(_registers(b24)) == 2


def test_no_line_number_means_no_extra_retry(b24: Bitrix, call: CallRecord) -> None:
    call.audios.all().delete()
    b24.fail[REGISTER] = 1
    with pytest.raises(providers.ProviderError):
        _send(call)
    assert len(_registers(b24)) == 1


def test_mapped_user_fallback_keeps_line_number(
    b24: Bitrix, sim_call: CallRecord, operator: OperatorProfile
) -> None:
    # Mapped user rejected on both line attempts → fallback user, line again.
    b24.fail[REGISTER] = 2
    _send(sim_call, user_map={str(operator.pk): "21"})
    users = [(p["USER_ID"], "LINE_NUMBER" in p) for p in _registers(b24)]
    assert users == [(21, True), (21, False), (7, True)]


def test_dispatch_end_to_end(company: Company, b24: Bitrix, sim_call: CallRecord) -> None:
    CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": HOOK, "create_card": "none"},
    )
    assert tasks.dispatch_call(sim_call.pk) == 1
    assert _registers(b24)[0]["LINE_NUMBER"] == "+998998887766"
