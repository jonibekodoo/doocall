"""Admin portal CRUD for the CRM catalog grid (platform staff)."""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.api import storage
from apps.api.errors import ApiError, ErrorCode
from apps.core.models import AuditLog
from apps.partners.permissions import IsPlatformStaff

from .models import CrmCatalogEntry

MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}


def logo_public_url(entry: CrmCatalogEntry) -> str | None:
    """RELATIVE path on purpose: every page that renders the grid (landing,
    cabinet subdomains, app.doocall.uz admin portal) proxies /api/public/*
    to this backend, and same-origin <img> loads are the only ones that
    survive users' ad-block/privacy extensions (cross-origin image loads —
    including the old presigned files.* redirect — get blocked)."""
    if not entry.logo_key:
        return None
    return f"/api/public/crm-logo/{entry.pk}"


def _entry_body(entry: CrmCatalogEntry) -> dict[str, Any]:
    return {
        "id": entry.pk,
        "name": entry.name,
        "site_url": entry.site_url,
        "logo_url": logo_public_url(entry),
        "sort_order": entry.sort_order,
        "is_active": entry.is_active,
    }


def _store_logo(entry_name: str, upload: Any) -> str:
    if upload.size > MAX_LOGO_BYTES:
        raise ApiError(ErrorCode.MISSING_FIELD, "logo too large (max 2MB)", 400)
    content_type = getattr(upload, "content_type", "") or ""
    if content_type not in ALLOWED_LOGO_TYPES:
        raise ApiError(ErrorCode.MISSING_FIELD, "logo must be png/jpeg/svg/webp", 400)
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/webp": "webp"}[
        content_type
    ]
    key = f"crm-catalog/{uuid.uuid4().hex}.{ext}"
    payload = upload.read()
    storage.ensure_bucket()
    import io

    storage.client().put_object(
        settings.MINIO_BUCKET,
        key,
        io.BytesIO(payload),
        length=len(payload),
        content_type=content_type,
    )
    return key


class AdminCrmCatalogView(APIView):
    permission_classes = [IsPlatformStaff]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(summary="List CRM catalog tiles (incl. inactive)")
    def get(self, request: Request) -> Response:
        return Response(
            {"success": True, "entries": [_entry_body(e) for e in CrmCatalogEntry.objects.all()]}
        )

    @extend_schema(summary="Add a CRM tile (multipart: name, site_url, logo)")
    def post(self, request: Request) -> Response:
        name = str(request.data.get("name") or "").strip()
        site_url = str(request.data.get("site_url") or "").strip()
        if not name or not site_url.startswith(("http://", "https://")):
            raise ApiError(ErrorCode.MISSING_FIELD, "name and http(s) site_url required", 400)
        if CrmCatalogEntry.objects.filter(name__iexact=name).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "name already exists", 400)
        logo = request.FILES.get("logo")
        logo_key = _store_logo(name, logo) if logo else ""
        try:
            sort_order = int(request.data.get("sort_order") or 100)
        except (TypeError, ValueError):
            sort_order = 100
        entry = CrmCatalogEntry.objects.create(
            name=name, site_url=site_url, logo_key=logo_key, sort_order=sort_order
        )
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.crm_catalog_added",
            target_model="integrations.CrmCatalogEntry",
            target_id=str(entry.pk),
            changes={"name": name},
        )
        return Response(
            {"success": True, "entry": _entry_body(entry)}, status=http.HTTP_201_CREATED
        )


class AdminCrmCatalogDetailView(APIView):
    permission_classes = [IsPlatformStaff]
    parser_classes = [MultiPartParser, FormParser]

    def _get(self, entry_id: int) -> CrmCatalogEntry:
        entry = CrmCatalogEntry.objects.filter(pk=entry_id).first()
        if entry is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "entry not found", 404)
        return entry

    @extend_schema(summary="Update a CRM tile (multipart; logo optional)")
    def post(self, request: Request, entry_id: int) -> Response:
        entry = self._get(entry_id)
        if name := str(request.data.get("name") or "").strip():
            entry.name = name
        if site_url := str(request.data.get("site_url") or "").strip():
            if not site_url.startswith(("http://", "https://")):
                raise ApiError(ErrorCode.MISSING_FIELD, "site_url must be http(s)", 400)
            entry.site_url = site_url
        if "sort_order" in request.data:
            try:
                entry.sort_order = int(request.data["sort_order"])
            except (TypeError, ValueError):
                raise ApiError(ErrorCode.MISSING_FIELD, "sort_order invalid", 400) from None
        if "is_active" in request.data:
            entry.is_active = str(request.data["is_active"]).lower() in ("1", "true", "yes")
        if logo := request.FILES.get("logo"):
            entry.logo_key = _store_logo(entry.name, logo)
        entry.save()
        return Response({"success": True, "entry": _entry_body(entry)})

    @extend_schema(summary="Delete a CRM tile")
    def delete(self, request: Request, entry_id: int) -> Response:
        entry = self._get(entry_id)
        AuditLog.objects.create(
            actor=cast(User, request.user),
            action="admin.crm_catalog_deleted",
            target_model="integrations.CrmCatalogEntry",
            target_id=str(entry.pk),
            changes={"name": entry.name},
        )
        entry.delete()
        return Response({"success": True})
