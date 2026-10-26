"""Celery dispatch: push finished calls into every enabled CRM integration."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.calls.models import CallRecord

from . import providers
from .models import CrmDelivery, CrmIntegration

logger = logging.getLogger(__name__)


def deliver(
    integration: CrmIntegration,
    record: CallRecord,
    record_url: str | None,
    *,
    is_retry: bool = False,
) -> CrmDelivery:
    """Push one call into one CRM and write the per-call audit row.

    The integration's ``last_*`` fields keep the quick "is it healthy?"
    summary; ``CrmDelivery`` is the full history. Exceptions are swallowed
    into the row — callers never see them, so one failing CRM can't stop
    delivery to the others. Kotib's 410 (switched off on their side)
    disables the integration so we stop posting to a dead URL."""
    update_fields = ["last_status", "last_error", "last_delivery_at"]
    # The sender works on a COPY: a delivery never writes the whole config
    # back (the admin may disconnect or re-save while a slow send runs).
    config_before = dict(integration.config)
    work = dict(integration.config)
    note = ""
    try:
        note = providers.send_call(integration.provider, work, record, record_url) or ""
        status, error = CrmDelivery.Status.OK, note[:500]
    except providers.CallSkipped as exc:
        # The integration's own options exclude this call — not a failure.
        status, error = CrmDelivery.Status.OK, f"skipped: {exc}"[:500]
    except providers.KotibGone:
        status, error = CrmDelivery.Status.ERROR, providers.KOTIB_GONE_ERROR
        if _disable_kotib(integration.pk, config_before.get("webhook_url")):
            integration.is_enabled = False
            logger.warning("integration %s/kotib disabled: Kotib answered 410", record.company_id)
    except Exception as exc:  # noqa: BLE001 - keep other CRMs delivering
        status, error = CrmDelivery.Status.ERROR, str(exc)[:500]
        logger.warning(
            "integration %s/%s failed for call %s: %s",
            record.company_id,
            integration.provider,
            record.pk,
            exc,
        )
    # Bitrix24 CRM-mode cache refreshed by the sender: merge just those keys.
    cache = {
        key: work[key]
        for key in providers.B24_MODE_CACHE_KEYS
        if key in work and work[key] != config_before.get(key)
    }
    if cache and _merge_cache(integration.pk, cache, config_before.get("webhook_url")):
        integration.config = {**integration.config, **cache}
    integration.last_status = status
    # Errors, or a success warning (note) — never the "skipped" marker.
    integration.last_error = error if status == CrmDelivery.Status.ERROR else note[:500]
    integration.last_delivery_at = timezone.now()
    integration.save(update_fields=update_fields)
    return CrmDelivery.all_objects.create(
        company=record.company,
        call=record,
        provider=integration.provider,
        status=status,
        error=error,
        is_retry=is_retry,
        external_id=str(work.get(providers.DELIVERY_EXTERNAL_ID) or "")
        if status == CrmDelivery.Status.OK
        else "",
    )


def _locked_current(pk: int, sent_to: Any) -> CrmIntegration | None:
    """The integration row, locked, if it is still enabled and still points
    at the URL the delivery used (else a disconnect/re-save happened)."""
    row: CrmIntegration | None = (
        CrmIntegration.all_objects.select_for_update().filter(pk=pk).first()
    )
    if row is None or not row.is_enabled or row.config.get("webhook_url") != sent_to:
        return None
    return row


def _merge_cache(pk: int, cache: dict[str, Any], sent_to: Any) -> bool:
    """Merge cache keys into the CURRENT stored config (dropped if stale)."""
    with transaction.atomic():
        row = _locked_current(pk, sent_to)
        if row is None:
            return False
        row.config = {**row.config, **cache}
        row.save(update_fields=["config"])
        return True


def _disable_kotib(pk: int, sent_to: Any) -> bool:
    """Kotib 410: disable + revoke Kotib's public-API key on the CURRENT
    row — unless it was meanwhile disconnected or reconnected elsewhere."""
    with transaction.atomic():
        row = _locked_current(pk, sent_to)
        if row is None:
            return False
        row.is_enabled = False
        row.config = {k: v for k, v in row.config.items() if k != "doocall_api_key"}
        row.save(update_fields=["is_enabled", "config", "updated_at"])
        return True


def record_signature(server_id_hex: str) -> str:
    """Stable HMAC that lets CRMs hold a permanent recording link."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f"rec:{server_id_hex}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def public_record_url(record: CallRecord) -> str | None:
    """Permanent public URL (302 → fresh presigned MinIO URL) for the audio."""
    if not record.audios.exists():
        return None
    sid = record.server_id.hex
    host = f"{record.company.slug}.{settings.DOMAIN_ROOT}"
    scheme = getattr(settings, "URL_SCHEME", "https")
    return f"{scheme}://{host}/api/public/rec/{sid}?sig={record_signature(sid)}"


@shared_task(name="apps.integrations.tasks.dispatch_call")
def dispatch_call(record_id: int) -> int:
    """Send one call to every enabled integration; failures are recorded
    per-integration (no task-level retry — that would double-post to the
    CRMs that already succeeded)."""
    record = (
        CallRecord.all_objects.select_related("company", "operator")
        .filter(pk=record_id)
        .first()
    )
    if record is None:
        return 0
    integrations = CrmIntegration.all_objects.filter(company=record.company, is_enabled=True)
    record_url = public_record_url(record)
    sent = 0
    for integration in integrations:
        if integration.provider == CrmIntegration.Provider.KOTIB and not providers.kotib_wants(
            record
        ):
            continue  # Kotib ignores missed/zero-length calls — no delivery row
        if deliver(integration, record, record_url).status == CrmDelivery.Status.OK:
            sent += 1
    return sent


def _late_bitrix24(integration: CrmIntegration, record: CallRecord, record_url: str) -> str:
    """Attach a late recording to the Bitrix24 call registered earlier."""
    delivery = (
        CrmDelivery.all_objects.filter(
            call=record, provider=CrmIntegration.Provider.BITRIX24, status=CrmDelivery.Status.OK
        )
        .exclude(external_id="")
        .order_by("-created_at", "-id")
        .first()
    )
    if delivery is None:
        return "skipped"  # never delivered, or delivered before CALL_IDs were stored
    try:
        attached = providers._b24_attach_recording(
            dict(integration.config), {"CALL_ID": delivery.external_id}, record, record_url
        )
    except Exception as exc:  # noqa: BLE001 - report, never break the upload
        logger.warning(
            "late audio bitrix24 attach failed for call %s: %s", record.pk, type(exc).__name__
        )
        return "error"
    return "attached" if attached in ("mp3", "wav") else "error"


@shared_task(name="apps.integrations.tasks.attach_late_audio")
def attach_late_audio(record_id: int) -> str:
    """A recording reached an already-delivered call: attach it where the
    CRM supports that (Bitrix24, via the stored telephony CALL_ID). Kotib
    reads record_url from calls.get itself; amoCRM/Odoo/webhook: no change."""
    record = CallRecord.all_objects.select_related("company").filter(pk=record_id).first()
    if record is None:
        return "skipped"
    record_url = public_record_url(record)
    integration = CrmIntegration.all_objects.filter(
        company=record.company, provider=CrmIntegration.Provider.BITRIX24, is_enabled=True
    ).first()
    outcome = "skipped"
    if integration is not None and record_url:
        outcome = _late_bitrix24(integration, record, record_url)
    logger.info("late audio company=%s call=%s bitrix24=%s", record.company_id, record.pk, outcome)
    return outcome
