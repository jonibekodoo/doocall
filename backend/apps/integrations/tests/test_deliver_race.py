"""deliver() never writes a stale config back: a disconnect or re-save that
happens while a (slow) send runs wins; only the Bitrix24 CRM-mode cache keys
are merged, and only into the still-current row."""

from __future__ import annotations

from typing import Any

import pytest

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db

HOOK = "https://acme.bitrix24.ru/rest/1/tok/"
NEW_HOOK = "https://other.bitrix24.ru/rest/2/tok2/"


@pytest.fixture
def bitrix(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": HOOK, "user_id": "7"},
    )


def _sender(monkeypatch: pytest.MonkeyPatch, during: Any = None) -> list[dict[str, Any]]:
    """A send that refreshes the mode cache (like a real Bitrix24 send) and
    runs ``during(config)`` mid-flight to simulate a concurrent admin."""
    seen: list[dict[str, Any]] = []

    def fake(provider: str, config: dict[str, Any], record: Any, url: Any) -> None:
        seen.append(dict(config))
        if during is not None:
            during()
        config.update(
            crm_mode="simple",
            crm_mode_checked_at="2026-10-15T00:00:00+00:00",
            crm_mode_assumed=False,
        )
        config["webhook_url"] = "https://tampered.example/"  # never written back

    monkeypatch.setattr(providers, "send_call", fake)
    return seen


def test_normal_path_merges_only_cache_keys(
    bitrix: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sender(monkeypatch)
    tasks.deliver(bitrix, call, None)
    bitrix.refresh_from_db()
    assert bitrix.config == {
        "webhook_url": HOOK,
        "user_id": "7",
        "crm_mode": "simple",
        "crm_mode_checked_at": "2026-10-15T00:00:00+00:00",
        "crm_mode_assumed": False,
    }
    assert bitrix.last_status == "ok"


def test_disconnect_during_send_keeps_config_empty(
    bitrix: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disconnect() -> None:
        CrmIntegration.all_objects.filter(pk=bitrix.pk).update(is_enabled=False, config={})

    _sender(monkeypatch, disconnect)
    tasks.deliver(bitrix, call, None)
    bitrix.refresh_from_db()
    assert bitrix.config == {} and bitrix.is_enabled is False


def test_resave_during_send_keeps_new_settings(
    bitrix: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    new = {"webhook_url": NEW_HOOK, "user_id": "9", "create_card": "contact"}

    def resave() -> None:
        CrmIntegration.all_objects.filter(pk=bitrix.pk).update(config=new)

    _sender(monkeypatch, resave)
    tasks.deliver(bitrix, call, None)
    bitrix.refresh_from_db()
    assert bitrix.config == new  # mode detected for the OLD portal is dropped too


def test_same_url_option_change_during_send_is_kept(
    bitrix: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def change_option() -> None:
        CrmIntegration.all_objects.filter(pk=bitrix.pk).update(
            config={"webhook_url": HOOK, "user_id": "7", "only_answered": True}
        )

    _sender(monkeypatch, change_option)
    tasks.deliver(bitrix, call, None)
    bitrix.refresh_from_db()
    assert bitrix.config["only_answered"] is True  # admin's change survives
    assert bitrix.config["crm_mode"] == "simple"  # cache merged into it
    assert bitrix.config["webhook_url"] == HOOK


def test_sender_mutations_never_reach_the_in_memory_object(
    bitrix: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sender(monkeypatch)
    tasks.deliver(bitrix, call, None)
    assert bitrix.config["webhook_url"] == HOOK


# ── Kotib 410 auto-disable uses the same guard ────────────────────────────
@pytest.fixture
def kotib(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="kotib",
        is_enabled=True,
        config={
            "api_key": "k" * 20,
            "webhook_url": "https://kotib.test/api/v1/integration/doocall/a/webhook",
            "webhook_secret": "s" * 64,
            "doocall_api_key": "d" * 32,
        },
    )


def _gone(monkeypatch: pytest.MonkeyPatch, during: Any = None) -> None:
    def fake(provider: str, config: dict[str, Any], record: Any, url: Any) -> None:
        if during is not None:
            during()
        raise providers.KotibGone(providers.KOTIB_GONE_ERROR)

    monkeypatch.setattr(providers, "send_call", fake)


def test_kotib_gone_disables_current_row(
    kotib: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gone(monkeypatch)
    tasks.deliver(kotib, call, None)
    kotib.refresh_from_db()
    assert kotib.is_enabled is False and "doocall_api_key" not in kotib.config
    assert kotib.config["api_key"] == "k" * 20


def test_kotib_gone_after_reconnect_does_not_touch_new_connection(
    kotib: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh = {
        "api_key": "n" * 20,
        "webhook_url": "https://kotib.test/api/v1/integration/doocall/b/webhook",
        "webhook_secret": "t" * 64,
        "doocall_api_key": "e" * 32,
    }

    def reconnect() -> None:
        CrmIntegration.all_objects.filter(pk=kotib.pk).update(config=fresh)

    _gone(monkeypatch, reconnect)
    tasks.deliver(kotib, call, None)
    kotib.refresh_from_db()
    assert kotib.is_enabled is True and kotib.config == fresh


def test_kotib_gone_after_disconnect_keeps_config_empty(
    kotib: CrmIntegration, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disconnect() -> None:
        CrmIntegration.all_objects.filter(pk=kotib.pk).update(is_enabled=False, config={})

    _gone(monkeypatch, disconnect)
    tasks.deliver(kotib, call, None)
    kotib.refresh_from_db()
    assert kotib.config == {} and kotib.is_enabled is False
