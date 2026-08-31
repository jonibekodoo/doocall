"""Public (unauthenticated) endpoints for the landing site."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import PricingSetting

PRICING_CACHE_KEY = "public:pricing"


def pricing_cache_ttl() -> int:
    return int(getattr(settings, "PUBLIC_PRICING_CACHE_SECONDS", 60))


class PublicPricingView(APIView):
    """GET /api/public/pricing/ — current global pricing, cached, no auth."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Public pricing (cached)")
    def get(self, request: Request) -> Response:
        body = cache.get(PRICING_CACHE_KEY)
        if body is None:
            row = PricingSetting.objects.filter(company=None).first()
            body = {
                "success": True,
                "price_per_operator_uzs": row.price_per_operator_uzs
                if row
                else int(settings.DEFAULT_PRICE_PER_OPERATOR_UZS),
                "trial_days": row.trial_days if row else int(settings.TRIAL_DAYS),
                "currency": "UZS",
            }
            cache.set(PRICING_CACHE_KEY, body, pricing_cache_ttl())
        return Response(body)


class PublicAppLatestView(APIView):
    """GET /api/public/app/latest — newest APK metadata (no auth)."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Latest mobile APK metadata")
    def get(self, request: Request) -> Response:
        from apps.core.models import AppRelease

        release = AppRelease.objects.first()
        if release is None:
            return Response({"success": True, "release": None})
        return Response(
            {
                "success": True,
                "release": {
                    "version": release.version,
                    "size_bytes": release.size_bytes,
                    "notes": release.notes,
                    "released_at": release.created_at.isoformat(),
                },
            }
        )


class PublicAppDownloadView(APIView):
    """GET /api/public/app/download — 302 to a presigned APK URL."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Download the latest APK (redirect)")
    def get(self, request: Request) -> Any:
        from django.http import HttpResponseNotFound, HttpResponseRedirect

        from apps.api import storage
        from apps.core.models import AppRelease

        release = AppRelease.objects.first()
        if release is None:
            return HttpResponseNotFound("no app release yet")
        return HttpResponseRedirect(storage.presigned_url(release.object_key))
