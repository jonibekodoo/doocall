"""Celery tasks for the web cabinet: calls export + signed call webhooks."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.api import storage
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core import netguard
from apps.core.tenancy import tenant_context

from .models import ExportJob

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "call_id",
    "start_time_local",
    "call_type",
    "call_status",
    "operator_number",
    "counterparty_number",
    "counterparty_name",
    "resolved_name",
    "duration",
    "sim_slot",
]


def _export_rows(job: ExportJob) -> Any:
    """The filtered queryset, values()-projected — streaming, no model objects."""
    from .views_calls import filtered_calls  # local import avoids a cycle

    with tenant_context(job.company_id):
        return filtered_calls(job.filters).order_by("-start_time").values(*EXPORT_COLUMNS)


def _build_csv(rows: Any) -> tuple[bytes, int]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    count = 0
    for row in rows.iterator(chunk_size=2000):
        writer.writerow(row)
        count += 1
    return buffer.getvalue().encode("utf-8-sig"), count


def _build_xlsx(rows: Any) -> tuple[bytes, int]:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("calls")
    ws.append(EXPORT_COLUMNS)
    count = 0
    for row in rows.iterator(chunk_size=2000):
        ws.append([row[c] for c in EXPORT_COLUMNS])
        count += 1
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), count


@shared_task(name="apps.web.tasks.run_export")
def run_export(job_id: int) -> int:
    job = ExportJob.all_objects.filter(pk=job_id).first()
    if job is None:  # pragma: no cover - race with delete
        return 0
    try:
        rows = _export_rows(job)
        payload, count = (
            _build_xlsx(rows) if job.format == ExportJob.Format.XLSX else _build_csv(rows)
        )
        stamp = timezone.now().strftime("%Y%m%d%H%M%S")
        key = f"exports/{job.company_id}/calls-{stamp}-{job.pk}.{job.format}"
        storage.store_audio(key, payload, f"calls.{job.format}")  # generic object PUT
        job.object_key = key
        job.row_count = count
        job.status = ExportJob.Status.DONE
    except Exception as exc:  # noqa: BLE001 - job must record any failure
        job.status = ExportJob.Status.FAILED
        job.error = str(exc)[:2000]
        logger.exception("export %s failed", job_id)
    job.finished_at = timezone.now()
    job.save()
    return int(job.row_count)


def sign_webhook(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def webhook_payload(record: CallRecord) -> dict[str, Any]:
    return {
        "event": "call.received",
        "call_id": record.call_id,
        "server_id": f"srv_{record.server_id.hex}",
        "call_type": record.call_type,
        "call_status": record.call_status,
        "from": record.from_number,
        "to": record.to_number,
        "counterparty_number": record.counterparty_number,
        "counterparty_name": record.resolved_name or record.counterparty_name,
        "duration": record.duration,
        "start_time": record.start_time.isoformat(),
        "received_at": record.received_at.isoformat(),
    }


WEBHOOK_BLOCKED_HINT = "Sozlamalar → Integratsiya bo'limida webhook manzilini tuzating"


class WebhookBlocked(Exception):
    """Delivery refused for good (SSRF policy / redirect) — never retried."""


def deliver_webhook(company: Company, payload: dict[str, Any], *, timeout: int = 10) -> int:
    """POST the signed payload to the company's webhook URL. Returns HTTP status.

    The URL is customer-typed, so it goes through the SSRF guard
    (``netguard.open_url``: public https host, pinned IP, no redirects, no
    env proxies). A policy block or a redirect raises :class:`WebhookBlocked`
    (permanent); HTTP/connection errors propagate for the task's retries."""
    body = json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - URL is company-configured
        company.webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Doocall-Signature": sign_webhook(company.webhook_secret, body),
            "User-Agent": "dooCall-webhook/1.0",
        },
        method="POST",
    )
    try:
        with netguard.open_url(request, timeout=timeout) as response:
            return int(response.status)
    except netguard.UnsafeURL as exc:
        raise WebhookBlocked(
            f"Webhook manzili xavfsizlik tekshiruvidan o'tmadi: {exc} — {WEBHOOK_BLOCKED_HINT}"
        ) from None
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise WebhookBlocked(
                f"Webhook manzili yo'naltirish (HTTP {exc.code}) qaytardi — "
                f"yo'naltirishlar kuzatilmaydi; {WEBHOOK_BLOCKED_HINT}"
            ) from None
        raise


@shared_task(
    name="apps.web.tasks.deliver_call_webhook",
    autoretry_for=(Exception,),
    retry_backoff=30,
    max_retries=3,
)
def deliver_call_webhook(record_id: int) -> int:
    record = CallRecord.all_objects.select_related("company").filter(pk=record_id).first()
    if record is None or not record.company.webhook_url:
        return 0
    try:
        return deliver_webhook(record.company, webhook_payload(record))
    except WebhookBlocked as exc:
        # Permanent: retrying can't help. Logged without the URL (may hold a token).
        logger.warning("webhook for company %s not sent: %s", record.company_id, exc)
        return 0
