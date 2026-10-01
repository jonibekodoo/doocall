"""Celery dispatch: push finished calls into every enabled CRM integration."""

from __future__ import annotations

import hashlib
import hmac
import logging

from celery import shared_task
from django.conf import settings
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
    delivery to the others."""
    try:
        providers.send_call(integration.provider, integration.config, record, record_url)
        status, error = CrmDelivery.Status.OK, ""
    except Exception as exc:  # noqa: BLE001 - keep other CRMs delivering
        status, error = CrmDelivery.Status.ERROR, str(exc)[:500]
        logger.warning(
            "integration %s/%s failed for call %s: %s",
            record.company_id,
            integration.provider,
            record.pk,
            exc,
        )
    integration.last_status = status
    integration.last_error = error
    integration.last_delivery_at = timezone.now()
    integration.save(update_fields=["last_status", "last_error", "last_delivery_at"])
    return CrmDelivery.all_objects.create(
        company=record.company,
        call=record,
        provider=integration.provider,
        status=status,
        error=error,
        is_retry=is_retry,
    )


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
        if deliver(integration, record, record_url).status == CrmDelivery.Status.OK:
            sent += 1
    return sent
