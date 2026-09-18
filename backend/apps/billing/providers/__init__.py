"""Payment provider registry."""

from __future__ import annotations

from .base import PaymentProvider, WebhookResult
from .click import ClickProvider
from .manual import ManualProvider
from .payme import PaymeProvider

# NOTE: Paylov has no webhook provider here on purpose. It is integrated via the
# direct Merchant API (apps.billing.paylov_api): balance is credited ONLY after
# Paylov confirms the OTP in BillingPaylovConfirmView. A webhook-style provider
# would add a second, Basic-Auth-only path that credits balance — never add one.
_PROVIDERS: dict[str, PaymentProvider] = {
    provider.name: provider for provider in (ManualProvider(), PaymeProvider(), ClickProvider())
}


def get_provider(name: str) -> PaymentProvider | None:
    return _PROVIDERS.get(name)


__all__ = [
    "ClickProvider",
    "ManualProvider",
    "PaymentProvider",
    "PaymeProvider",
    "WebhookResult",
    "get_provider",
]
