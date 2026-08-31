"""PaymentProvider interface.

Every provider (manual, Payme, Click, future ones) implements the same
three-step shape:

* ``verify(request)`` — authenticate/verify the webhook signature. MUST be
  called before ``handle``; a False return maps to the provider's own
  "bad signature" response, never to a processed payment.
* ``handle(request)`` — parse the callback, mutate Payment/Invoice/
  Subscription via :func:`apps.billing.services.apply_payment`, and return
  the provider-specific response body + HTTP status.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rest_framework.request import Request


@dataclass
class WebhookResult:
    body: dict[str, Any] = field(default_factory=dict)
    status_code: int = 200


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def verify(self, request: Request) -> bool:
        """True iff the callback is authentic (signature/credentials check)."""

    @abstractmethod
    def handle(self, request: Request) -> WebhookResult:
        """Process a VERIFIED callback."""

    @abstractmethod
    def bad_signature_response(self) -> WebhookResult:
        """Provider-specific response for a failed verification."""
