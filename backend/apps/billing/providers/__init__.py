"""Payment provider registry."""

from __future__ import annotations

from .base import PaymentProvider, WebhookResult
from .click import ClickProvider
from .manual import ManualProvider
from .payme import PaymeProvider

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
