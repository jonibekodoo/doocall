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
from .models import CrmIntegration

logger = logging.getLogger(__name__)


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
        try:
            providers.send_call(integration.provider, integration.config, record, record_url)
            integration.last_status = "ok"
            integration.last_error = ""
            sent += 1
        except Exception as exc:  # noqa: BLE001 - keep other CRMs delivering
            integration.last_status = "error"
            integration.last_error = str(exc)[:500]
            logger.warning(
                "integration %s/%s failed for call %s: %s",
                record.company_id,
                integration.provider,
                record_id,
                exc,
            )
        integration.last_delivery_at = timezone.now()
        integration.save(update_fields=["last_status", "last_error", "last_delivery_at"])
    return sent
