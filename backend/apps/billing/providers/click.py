"""Click adapter — SHOP-API prepare/complete callbacks, sandbox-shaped.

Protocol (https://docs.click.uz, SHOP-API):
* Click POSTs form/JSON params with ``action`` 0 (prepare) or 1 (complete).
* ``sign_string`` = md5(click_trans_id + service_id + SECRET_KEY +
  merchant_trans_id + amount + action + sign_time)
  (merchant_prepare_id is additionally included on complete).
* ``merchant_trans_id`` carries our Invoice.number.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from rest_framework.request import Request

from apps.billing.models import Invoice, Payment
from apps.billing.services import apply_payment

from .base import PaymentProvider, WebhookResult

ACTION_PREPARE = "0"
ACTION_COMPLETE = "1"

ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_NOT_FOUND = -5
ERR_UNKNOWN_ACTION = -3


def _params(request: Request) -> dict[str, str]:
    source: Any = request.data if request.data else request.query_params
    result: dict[str, str] = {}
    for key, value in dict(source).items():
        if isinstance(value, list):
            value = value[0] if value else ""
        result[key] = str(value)
    return result


class ClickProvider(PaymentProvider):
    name = "click"

    def _expected_sign(self, p: dict[str, str]) -> str:
        action = p.get("action", "")
        parts = [
            p.get("click_trans_id", ""),
            p.get("service_id", ""),
            settings.CLICK_SECRET_KEY,
        ]
        if action == ACTION_COMPLETE:
            parts += [p.get("merchant_trans_id", ""), p.get("merchant_prepare_id", "")]
        else:
            parts += [p.get("merchant_trans_id", "")]
        parts += [p.get("amount", ""), action, p.get("sign_time", "")]
        return hashlib.md5("".join(parts).encode()).hexdigest()  # noqa: S324 - Click mandates md5

    def verify(self, request: Request) -> bool:
        p = _params(request)
        if not settings.CLICK_SECRET_KEY:
            return False
        return p.get("sign_string", "") == self._expected_sign(p)

    def bad_signature_response(self) -> WebhookResult:
        return WebhookResult({"error": ERR_SIGN, "error_note": "SIGN CHECK FAILED"}, 200)

    def handle(self, request: Request) -> WebhookResult:
        p = _params(request)
        action = p.get("action", "")
        if action == ACTION_PREPARE:
            return self._prepare(p)
        if action == ACTION_COMPLETE:
            return self._complete(p)
        return WebhookResult({"error": ERR_UNKNOWN_ACTION, "error_note": "Action not found"})

    def _find_invoice(self, p: dict[str, str]) -> Invoice | None:
        invoice: Invoice | None = Invoice.all_objects.filter(
            number=p.get("merchant_trans_id", "")
        ).first()
        return invoice

    def _prepare(self, p: dict[str, str]) -> WebhookResult:
        invoice = self._find_invoice(p)
        if invoice is None:
            return WebhookResult({"error": ERR_NOT_FOUND, "error_note": "Order not found"})
        if float(p.get("amount", "0")) != float(invoice.total_uzs):
            return WebhookResult({"error": ERR_AMOUNT, "error_note": "Incorrect amount"})

        payment, _ = Payment.all_objects.get_or_create(
            provider=Payment.Provider.CLICK,
            external_id=p.get("click_trans_id", ""),
            defaults={
                "company": invoice.company,
                "invoice": invoice,
                "amount_uzs": invoice.total_uzs,
                "status": Payment.Status.PENDING,
            },
        )
        return WebhookResult(
            {
                "click_trans_id": p.get("click_trans_id", ""),
                "merchant_trans_id": invoice.number,
                "merchant_prepare_id": payment.pk,
                "error": 0,
                "error_note": "Success",
            }
        )

    def _complete(self, p: dict[str, str]) -> WebhookResult:
        payment = Payment.all_objects.filter(
            provider=Payment.Provider.CLICK, external_id=p.get("click_trans_id", "")
        ).first()
        if payment is None:
            return WebhookResult({"error": ERR_NOT_FOUND, "error_note": "Transaction not found"})
        if str(p.get("error", "0")) not in ("0", ""):
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            return WebhookResult(
                {
                    "click_trans_id": p.get("click_trans_id", ""),
                    "merchant_trans_id": p.get("merchant_trans_id", ""),
                    "error": 0,
                    "error_note": "Failure recorded",
                }
            )
        apply_payment(payment)
        return WebhookResult(
            {
                "click_trans_id": p.get("click_trans_id", ""),
                "merchant_trans_id": p.get("merchant_trans_id", ""),
                "merchant_confirm_id": payment.pk,
                "error": 0,
                "error_note": "Success",
            }
        )
