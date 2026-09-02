"""Public integration surface (moizvonki-style).

* ``POST /api/v1`` — single action endpoint for third-party systems.
  Auth rides in the JSON body: ``user_name`` (cabinet user e-mail) +
  ``api_key`` (the company API key from Settings → Integration).
* ``GET /api/public/rec/<server_id>?sig=…`` — permanent recording link
  (302 → fresh presigned MinIO URL) safe to store inside a CRM.
* ``GET /api/public/crm-logo/<id>`` — catalog tile logo (302 → MinIO).
"""

from __future__ import annotations

import hmac
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import OperatorProfile, User
from apps.api import storage
from apps.api.errors import ApiError, ErrorCode
from apps.calls.models import CallAudio, CallRecord
from apps.companies.models import Company
from apps.core import domains

from .models import CrmCatalogEntry
from .tasks import public_record_url, record_signature

MAX_LIMIT = 200


def _parse_ts(value: Any) -> datetime | None:
    """Accept unix seconds or ISO-8601 (both used by moizvonki clients)."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise ApiError(
            ErrorCode.MISSING_FIELD, f"invalid date: {value!r}", http.HTTP_400_BAD_REQUEST
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def _call_body(record: CallRecord) -> dict[str, Any]:
    return {
        "server_id": f"srv_{record.server_id.hex}",
        "call_id": record.call_id,
        "call_type": record.call_type,
        "call_status": record.call_status,
        "from": record.from_number,
        "to": record.to_number,
        "counterparty_number": record.counterparty_number,
        "counterparty_name": record.resolved_name or record.counterparty_name,
        "operator": record.operator.user_name if record.operator else None,
        "operator_number": record.operator_number,
        "duration": record.duration,
        "start_time": record.start_time.isoformat(),
        "received_at": record.received_at.isoformat(),
        "record_url": public_record_url(record),
    }


class CustomApiView(APIView):
    """POST-only action API: {"user_name", "api_key", "action", ...}."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_api"

    @extend_schema(summary="Company public API (moizvonki-style single endpoint)")
    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        api_key = str(data.get("api_key") or "").strip()
        user_name = str(data.get("user_name") or "").strip().lower()
        if not api_key or not user_name:
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                "user_name and api_key are required",
                http.HTTP_400_BAD_REQUEST,
            )
        company = Company.objects.filter(api_key=api_key).exclude(api_key="").first()
        if company is None:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED
            )
        member = User.objects.filter(company=company).filter(
            username__iexact=user_name
        ).first() or User.objects.filter(company=company, email__iexact=user_name).first()
        if member is None:
            raise ApiError(
                ErrorCode.INVALID_API_KEY,
                "user_name does not belong to this account",
                http.HTTP_401_UNAUTHORIZED,
            )
        # Same host↔tenant guard as the device API.
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and company.slug != sub:
            raise ApiError(
                ErrorCode.INVALID_API_KEY, "wrong company domain", http.HTTP_401_UNAUTHORIZED
            )

        action = str(data.get("action") or "").strip()
        handler = {
            "calls.list": self._calls_list,
            "calls.get": self._calls_get,
            "users.list": self._users_list,
            "account.info": self._account_info,
        }.get(action)
        if handler is None:
            raise ApiError(
                ErrorCode.MISSING_FIELD, f"unknown action {action!r}", http.HTTP_400_BAD_REQUEST
            )
        return handler(company, data)

    # ── actions ────────────────────────────────────────────────────────────
    def _calls_list(self, company: Company, data: dict[str, Any]) -> Response:
        qs = CallRecord.all_objects.filter(company=company).select_related("operator")
        if from_date := _parse_ts(data.get("from_date")):
            qs = qs.filter(start_time__gte=from_date)
        if to_date := _parse_ts(data.get("to_date")):
            qs = qs.filter(start_time__lte=to_date)
        if phone := str(data.get("phone") or "").strip():
            qs = qs.filter(counterparty_number__icontains=phone.lstrip("+"))
        if call_type := str(data.get("call_type") or "").strip():
            qs = qs.filter(call_type=call_type)
        try:
            offset = max(0, int(data.get("offset") or 0))
            limit = min(MAX_LIMIT, max(1, int(data.get("limit") or 50)))
        except (TypeError, ValueError):
            raise ApiError(
                ErrorCode.MISSING_FIELD, "offset/limit must be integers", 400
            ) from None
        total = qs.count()
        rows = list(qs.order_by("-start_time")[offset : offset + limit])
        return Response(
            {
                "success": True,
                "total": total,
                "offset": offset,
                "limit": limit,
                "calls": [_call_body(r) for r in rows],
            }
        )

    def _calls_get(self, company: Company, data: dict[str, Any]) -> Response:
        qs = CallRecord.all_objects.filter(company=company)
        record = None
        if server_id := str(data.get("server_id") or "").strip():
            record = qs.filter(server_id=server_id.removeprefix("srv_")).first()
        elif call_id := str(data.get("call_id") or "").strip():
            record = qs.filter(call_id=call_id).first()
        else:
            raise ApiError(ErrorCode.MISSING_FIELD, "server_id or call_id required", 400)
        if record is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "call not found", http.HTTP_404_NOT_FOUND)
        return Response({"success": True, "call": _call_body(record)})

    def _users_list(self, company: Company, data: dict[str, Any]) -> Response:
        rows = [
            {
                "user_name": p.user_name,
                "full_name": p.full_name,
                "is_active": p.is_active,
                "phones": [s.number for s in p.sim_cards.all()],
            }
            for p in OperatorProfile.all_objects.filter(company=company).prefetch_related(
                "sim_cards"
            )
        ]
        return Response({"success": True, "users": rows})

    def _account_info(self, company: Company, data: dict[str, Any]) -> Response:
        return Response(
            {
                "success": True,
                "account": {
                    "name": company.name,
                    "slug": company.slug,
                    "status": company.status,
                    "operators": OperatorProfile.all_objects.filter(
                        company=company, is_active=True
                    ).count(),
                },
            }
        )


class RecordRedirectView(View):
    """Permanent audio link: HMAC-guarded 302 to a fresh presigned URL."""

    def get(self, request: HttpRequest, rec_id: str) -> HttpResponse:
        rec_id = rec_id.replace("-", "").removeprefix("srv_")
        sig = request.GET.get("sig") or ""
        if not hmac.compare_digest(sig, record_signature(rec_id)):
            return HttpResponse(status=403)
        record = CallRecord.all_objects.filter(server_id=rec_id).first()
        if record is None:
            return HttpResponse(status=404)
        audio = (
            record.audios.filter(kind=CallAudio.Kind.PRIMARY).first() or record.audios.first()
        )
        if audio is None:
            return HttpResponse(status=404)
        return HttpResponseRedirect(storage.presigned_url(audio.object_key))


class CrmLogoView(View):
    def get(self, request: HttpRequest, entry_id: int) -> HttpResponse:
        entry = CrmCatalogEntry.objects.filter(pk=entry_id, is_active=True).first()
        if entry is None or not entry.logo_key:
            return HttpResponse(status=404)
        return HttpResponseRedirect(storage.presigned_url(entry.logo_key))
