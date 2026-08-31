"""Payme (Paycom) adapter — JSON-RPC merchant API, sandbox-shaped.

Protocol (https://developer.help.paycom.uz, Merchant API):
* Payme POSTs JSON-RPC to our endpoint with
  ``Authorization: Basic base64("Paycom:" + PAYME_SECRET_KEY)``.
* Amounts are in TIYIN (UZS × 100).
* We implement the minimal method set: CheckPerformTransaction,
  CreateTransaction, PerformTransaction, CancelTransaction, CheckTransaction.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from django.conf import settings
from rest_framework.request import Request

from apps.billing.models import Invoice, Payment
from apps.billing.services import apply_payment

from .base import PaymentProvider, WebhookResult

# Payme error codes (subset).
ERR_INVALID_AUTH = -32504
ERR_INVALID_AMOUNT = -31001
ERR_ORDER_NOT_FOUND = -31050
ERR_TRANSACTION_NOT_FOUND = -31003

STATE_CREATED = 1
STATE_PERFORMED = 2
STATE_CANCELED = -1


class PaymeProvider(PaymentProvider):
    name = "payme"

    def verify(self, request: Request) -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.removeprefix("Basic ").strip()).decode()
        except (binascii.Error, UnicodeDecodeError):
            return False
        secret = settings.PAYME_SECRET_KEY
        return bool(secret) and decoded == f"Paycom:{secret}"

    def bad_signature_response(self) -> WebhookResult:
        # Payme expects HTTP 200 with a JSON-RPC error envelope.
        return WebhookResult(
            {"error": {"code": ERR_INVALID_AUTH, "message": "Invalid authorization"}}, 200
        )

    def handle(self, request: Request) -> WebhookResult:
        payload: dict[str, Any] = request.data if isinstance(request.data, dict) else {}
        method = payload.get("method", "")
        params: dict[str, Any] = payload.get("params") or {}
        rpc_id = payload.get("id")

        handler = {
            "CheckPerformTransaction": self._check_perform,
            "CreateTransaction": self._create,
            "PerformTransaction": self._perform,
            "CancelTransaction": self._cancel,
            "CheckTransaction": self._check,
        }.get(method)
        if handler is None:
            return WebhookResult(
                {"id": rpc_id, "error": {"code": -32601, "message": f"Unknown method {method}"}}
            )
        result = handler(params)
        result.body.setdefault("id", rpc_id)
        return result

    # ── helpers ────────────────────────────────────────────────────────────
    def _find_invoice(self, params: dict[str, Any]) -> Invoice | None:
        number = (params.get("account") or {}).get("invoice_number", "")
        invoice: Invoice | None = Invoice.all_objects.filter(number=number).first()
        return invoice

    def _amount_matches(self, invoice: Invoice, params: dict[str, Any]) -> bool:
        return params.get("amount") == invoice.total_uzs * 100  # tiyin

    # ── JSON-RPC methods ───────────────────────────────────────────────────
    def _check_perform(self, params: dict[str, Any]) -> WebhookResult:
        invoice = self._find_invoice(params)
        if invoice is None:
            return WebhookResult(
                {"error": {"code": ERR_ORDER_NOT_FOUND, "message": "Invoice not found"}}
            )
        if not self._amount_matches(invoice, params):
            return WebhookResult(
                {"error": {"code": ERR_INVALID_AMOUNT, "message": "Invalid amount"}}
            )
        return WebhookResult({"result": {"allow": True}})

    def _create(self, params: dict[str, Any]) -> WebhookResult:
        invoice = self._find_invoice(params)
        if invoice is None:
            return WebhookResult(
                {"error": {"code": ERR_ORDER_NOT_FOUND, "message": "Invoice not found"}}
            )
        if not self._amount_matches(invoice, params):
            return WebhookResult(
                {"error": {"code": ERR_INVALID_AMOUNT, "message": "Invalid amount"}}
            )
        txn_id = str(params.get("id", ""))
        payment, _ = Payment.all_objects.get_or_create(
            provider=Payment.Provider.PAYME,
            external_id=txn_id,
            defaults={
                "company": invoice.company,
                "invoice": invoice,
                "amount_uzs": invoice.total_uzs,
                "status": Payment.Status.PENDING,
            },
        )
        return WebhookResult(
            {
                "result": {
                    "create_time": params.get("time", 0),
                    "transaction": str(payment.pk),
                    "state": STATE_CREATED,
                }
            }
        )

    def _perform(self, params: dict[str, Any]) -> WebhookResult:
        payment = Payment.all_objects.filter(
            provider=Payment.Provider.PAYME, external_id=str(params.get("id", ""))
        ).first()
        if payment is None:
            return WebhookResult(
                {"error": {"code": ERR_TRANSACTION_NOT_FOUND, "message": "Not found"}}
            )
        apply_payment(payment)
        payment.refresh_from_db()
        return WebhookResult(
            {
                "result": {
                    "perform_time": int(payment.approved_at.timestamp() * 1000)
                    if payment.approved_at
                    else 0,
                    "transaction": str(payment.pk),
                    "state": STATE_PERFORMED,
                }
            }
        )

    def _cancel(self, params: dict[str, Any]) -> WebhookResult:
        payment = Payment.all_objects.filter(
            provider=Payment.Provider.PAYME, external_id=str(params.get("id", ""))
        ).first()
        if payment is None:
            return WebhookResult(
                {"error": {"code": ERR_TRANSACTION_NOT_FOUND, "message": "Not found"}}
            )
        if payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.REJECTED
            payment.save(update_fields=["status"])
        return WebhookResult(
            {"result": {"cancel_time": 0, "transaction": str(payment.pk), "state": STATE_CANCELED}}
        )

    def _check(self, params: dict[str, Any]) -> WebhookResult:
        payment = Payment.all_objects.filter(
            provider=Payment.Provider.PAYME, external_id=str(params.get("id", ""))
        ).first()
        if payment is None:
            return WebhookResult(
                {"error": {"code": ERR_TRANSACTION_NOT_FOUND, "message": "Not found"}}
            )
        state = {
            Payment.Status.PENDING: STATE_CREATED,
            Payment.Status.APPROVED: STATE_PERFORMED,
            Payment.Status.REJECTED: STATE_CANCELED,
            Payment.Status.FAILED: STATE_CANCELED,
        }[Payment.Status(payment.status)]
        return WebhookResult({"result": {"transaction": str(payment.pk), "state": state}})
