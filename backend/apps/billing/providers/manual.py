"""Manual (bank-transfer) provider.

There is no webhook: an accountant records the transfer as a pending Payment
and a platform admin approves it in the Django admin. The approval action
calls :func:`apps.billing.services.apply_payment`, which settles the invoice
and (re)activates + extends the company — the full provider lifecycle.
"""

from __future__ import annotations

from rest_framework.request import Request

from .base import PaymentProvider, WebhookResult


class ManualProvider(PaymentProvider):
    name = "manual"

    def verify(self, request: Request) -> bool:  # pragma: no cover - no webhook
        return False

    def handle(self, request: Request) -> WebhookResult:  # pragma: no cover
        return WebhookResult({"detail": "manual provider has no webhook"}, 404)

    def bad_signature_response(self) -> WebhookResult:  # pragma: no cover
        return WebhookResult({"detail": "manual provider has no webhook"}, 404)
