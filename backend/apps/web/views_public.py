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


class PublicLegalView(APIView):
    """GET /api/public/legal/<kind>/ — privacy / terms / refund page (no auth).

    Content is admin-authored HTML already sanitised on save."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Public legal document")
    def get(self, request: Request, kind: str) -> Response:
        from apps.core.locale import request_locale
        from apps.partners.models import LEGAL_KINDS, get_legal_document, localized_content

        if kind not in LEGAL_KINDS:
            return Response({"success": False, "message": "unknown document"}, status=404)
        d = get_legal_document(kind)
        lang = request_locale(request)  # ?lang= → cookie → Accept-Language → uz
        return Response(
            {
                "success": True,
                "kind": d.kind,
                "lang": lang,
                "content": localized_content(d, lang),
                "version": d.version,
                "updated_at": d.updated_at.isoformat(),
            }
        )


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


class PublicIntegratorsView(APIView):
    """GET /api/public/integrators — published integrators for the landing
    'our integrators' section. No auth."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Public integrators list")
    def get(self, request: Request) -> Response:
        from apps.partners.models import Integrator

        rows = [
            {
                "name": i.company_name or i.name,
                "logo_url": f"/api/public/integrator-logo/{i.pk}" if i.logo_key else None,
            }
            for i in Integrator.objects.filter(
                is_public=True, status=Integrator.Status.ACTIVE
            ).order_by("name")
        ]
        return Response({"success": True, "integrators": rows})


class PublicIntegratorApplyView(APIView):
    """POST /api/public/integrator-apply — leave a 'become an integrator'
    request from the landing page. No auth. Lightly IP-throttled."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @extend_schema(summary="Submit integrator application (public)")
    def post(self, request: Request) -> Response:
        from apps.partners.models import IntegratorApplication

        ip = request.META.get("REMOTE_ADDR", "?")
        throttle_key = f"integrator-apply:{ip}"
        if cache.get(throttle_key):
            return Response(
                {"success": False, "error": "too_many_requests"}, status=429
            )

        data = request.data
        full_name = (data.get("full_name") or "").strip()[:200]
        phone = (data.get("phone") or "").strip()[:32]
        email = (data.get("email") or "").strip()[:254]
        company = (data.get("company") or "").strip()[:200]
        message = (data.get("message") or "").strip()[:2000]
        if len(full_name) < 2 or len(phone) < 5:
            return Response(
                {"success": False, "error": "name_and_phone_required"}, status=400
            )

        IntegratorApplication.objects.create(
            full_name=full_name,
            phone=phone,
            email=email,
            company=company,
            message=message,
        )
        cache.set(throttle_key, 1, timeout=30)
        return Response({"success": True}, status=201)
