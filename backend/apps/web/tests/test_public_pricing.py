"""Public pricing endpoint: unauthenticated, cached, returns current pricing."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.billing.models import PricingSetting
from apps.web.views_public import PRICING_CACHE_KEY

pytestmark = pytest.mark.django_db

URL = "/api/public/pricing/"


@pytest.fixture(autouse=True)
def _fresh_cache(settings: Any) -> None:
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.delete(PRICING_CACHE_KEY)


class TestPublicPricing:
    def test_unauthenticated_returns_current_pricing(self) -> None:
        response = APIClient().get(URL)  # no credentials whatsoever
        assert response.status_code == 200
        body = response.json()
        # Conftest's autouse _pricing fixture created the 50000/14 global row.
        assert body == {
            "success": True,
            "price_per_operator_uzs": 50000,
            "trial_days": 14,
            "currency": "UZS",
        }

    def test_response_is_cached_until_ttl(self) -> None:
        client = APIClient()
        assert client.get(URL).json()["price_per_operator_uzs"] == 50000

        # Admin raises the price — cached value keeps serving within TTL.
        row = PricingSetting.objects.get(company=None)
        row.price_per_operator_uzs = 90000
        row.save()
        assert client.get(URL).json()["price_per_operator_uzs"] == 50000

        # TTL expiry (simulated by cache invalidation) → new value.
        cache.delete(PRICING_CACHE_KEY)
        assert client.get(URL).json()["price_per_operator_uzs"] == 90000

    def test_falls_back_to_settings_defaults_without_pricing_row(self) -> None:
        PricingSetting.objects.all().delete()
        cache.delete(PRICING_CACHE_KEY)
        body = APIClient().get(URL).json()
        assert body["price_per_operator_uzs"] == 50000  # settings default
        assert body["trial_days"] == 14
