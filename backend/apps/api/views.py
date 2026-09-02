"""/api/call/v1 — the five mobile endpoints (contract §4–§8).

All endpoints: POST + JSON only, §9 envelope, api_key in body or Bearer
header, per-scope throttling, 402 when the company is suspended/expired.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Device, OperatorProfile, SimCard
from apps.calls.models import AppLog, CallAudio, CallRecord, ContactPhone
from apps.core.phone import normalize_phone

from . import storage
from .auth import authenticate_device, require_active_company
from .errors import ApiError, ErrorCode
from .serializers import (
    AuthRequestSerializer,
    CallsListRequestSerializer,
    LogRequestSerializer,
    StatsRequestSerializer,
    UploadRequestSerializer,
)

DEVICE_TZ = ZoneInfo(settings.TIME_ZONE)  # device-local == server TZ assumption (§1)


def _enqueue_webhook(record_id: int) -> None:
    from apps.web.tasks import deliver_call_webhook

    deliver_call_webhook.delay(record_id)


def _enqueue_crm_dispatch(record_id: int) -> None:
    from apps.integrations.tasks import dispatch_call

    dispatch_call.delay(record_id)


def _server_id(record: CallRecord) -> str:
    return f"srv_{record.server_id.hex}"


def _parse_local(value: str) -> datetime | None:
    """Parse the §1 'yyyy-MM-dd HH:mm:ss' device-local string to aware UTC."""
    if not value:
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ApiError(
            ErrorCode.MISSING_FIELD,
            f"Invalid datetime format: {value!r} (expected 'yyyy-MM-dd HH:mm:ss')",
            http.HTTP_400_BAD_REQUEST,
        ) from None
    return naive.replace(tzinfo=DEVICE_TZ).astimezone(ZoneInfo("UTC"))


class BaseApiView(APIView):
    """POST-only, no session auth, scoped throttling."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]


class AuthView(BaseApiView):
    """§4 — the ONLY auth call; onboarding data rides along and is upserted."""

    throttle_scope = "auth"

    @extend_schema(
        request=AuthRequestSerializer,
        responses={200: OpenApiResponse(description='{"success": true, "api_key": "..."}')},
        summary="Device login (contract §4)",
    )
    def post(self, request: Request) -> Response:
        serializer = AuthRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        operator = (
            OperatorProfile.all_objects.select_related("company", "user")
            .filter(user_name=data["username"], is_active=True)
            .first()
        )
        if operator is None or not check_password(data["password"], operator.user.password):
            # Exact legacy 401 body (§4) + §9 taxonomy fields.
            return Response(
                {
                    "success": False,
                    "api_key": "",
                    "message": "invalid credentials",
                    "error_code": ErrorCode.INVALID_CREDENTIALS,
                },
                status=http.HTTP_401_UNAUTHORIZED,
            )

        require_active_company(operator.company)

        with transaction.atomic():
            if data["full_name"]:
                operator.full_name = data["full_name"]
                operator.save(update_fields=["full_name"])

            for entry in data["phone_numbers"]:
                SimCard.all_objects.update_or_create(
                    company=operator.company,
                    operator=operator,
                    sim_slot=entry["sim_slot"],
                    defaults={"number": normalize_phone(entry["number"]), "is_active": True},
                )

            device_info = data["device"]
            if device_info:
                Device.all_objects.update_or_create(
                    company=operator.company,
                    operator=operator,
                    device_id=device_info["device_id"],
                    defaults={
                        "model": device_info["model"],
                        "manufacturer": device_info["manufacturer"],
                        "app_version": device_info["app_version"],
                        "os_version": device_info["os_version"],
                        "last_seen_at": timezone.now(),
                    },
                )

        # Byte-compatible §4 success body.
        return Response({"success": True, "api_key": operator.api_key})


class UploadView(BaseApiView):
    """§5 — full CDR + Base64 audio → MinIO."""

    throttle_scope = "upload"

    @extend_schema(
        request=UploadRequestSerializer,
        responses={200: OpenApiResponse(description="§5.4 envelope")},
        summary="Upload one call record (contract §5)",
    )
    def post(self, request: Request) -> Response:
        operator = authenticate_device(request)
        serializer = UploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company = operator.company

        call_id = data["call_id"]
        existing = CallRecord.all_objects.filter(company=company, call_id=call_id).first()
        if existing is not None:
            # §5.4 duplicate envelope — 409.
            raise ApiError(
                ErrorCode.DUPLICATE_CALL_ID,
                "call_id already exists",
                http.HTTP_409_CONFLICT,
                extra={"status": "already_exists", "call_id": call_id},
            )

        # ── Audio payloads first: size violations must not create rows ─────
        audio_items = []
        for kind, filename_field, payload_field in (
            (CallAudio.Kind.PRIMARY, "audio_filename", "audio_file"),
            (CallAudio.Kind.REALTIME, "audio_filename_realtime", "audio_file_realtime"),
        ):
            filename = data.get(filename_field) or ""
            payload_b64 = data.get(payload_field)
            if not payload_b64 or filename in ("", "none"):
                continue
            try:
                payload = base64.b64decode(payload_b64, validate=True)
            except (binascii.Error, ValueError):
                raise ApiError(
                    ErrorCode.MISSING_FIELD,
                    f"{payload_field} is not valid Base64",
                    http.HTTP_400_BAD_REQUEST,
                ) from None
            max_bytes = settings.AUDIO_MAX_MB * 1024 * 1024
            if len(payload) > max_bytes:
                raise ApiError(
                    ErrorCode.AUDIO_TOO_LARGE,
                    f"Audio exceeds the {settings.AUDIO_MAX_MB}MB limit",
                    http.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    extra={"status": "error", "call_id": call_id},
                )
            audio_items.append((kind, filename, payload))

        # ── Normalize numbers (contract §1 — Phase 2 shared utility) ───────
        from_number = normalize_phone(data["from"])
        to_number = normalize_phone(data["to"])
        operator_number = normalize_phone(data.get("operator_number") or "") or None
        counterparty_number = normalize_phone(data["counterparty_number"])

        # ── Backend contact catalogue → resolved_name (§5.4) ───────────────
        contact_phone = (
            ContactPhone.objects.filter(contact__company=company, number=counterparty_number)
            .select_related("contact")
            .first()
        )
        resolved_name = contact_phone.contact.name if contact_phone else None

        start_utc = _parse_local(data["start_time"])
        if start_utc is None:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "start_time is required", http.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            record = CallRecord.all_objects.create(
                company=company,
                operator=operator,
                call_id=call_id,
                call_type=data["call_type"],
                call_status=data["call_status"],
                from_number=from_number,
                from_name=data.get("from_name") or None,
                to_number=to_number,
                to_name=data.get("to_name") or None,
                operator_number=operator_number,
                operator_number_missing=bool(data.get("operator_number_missing"))
                or operator_number is None,
                counterparty_number=counterparty_number,
                counterparty_name=data.get("counterparty_name") or None,
                resolved_name=resolved_name,
                sim_slot=data["sim_slot"],
                duration=data["duration"],
                start_time=start_utc,
                end_time=_parse_local(data["end_time"]),
                start_time_local=data["start_time"],
                end_time_local=data["end_time"],
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                address=data.get("address") or "",
            )

            audio_body: dict[str, Any] = {"stored": False, "url": None, "size_bytes": 0}
            for kind, filename, payload in audio_items:
                object_key = f"{company.pk}/{call_id}/{kind}/{filename}"
                url = storage.store_audio(object_key, payload, filename)
                CallAudio.objects.create(
                    call=record,
                    kind=kind,
                    filename=filename,
                    object_key=object_key,
                    size_bytes=len(payload),
                )
                if kind == CallAudio.Kind.PRIMARY:
                    audio_body = {"stored": True, "url": url, "size_bytes": len(payload)}

            # Signed outbound webhook (Phase 5): fires after commit only.
            if company.webhook_url:
                record_id = record.pk
                transaction.on_commit(partial(_enqueue_webhook, record_id))

            # CRM connectors (amoCRM/Bitrix24/Odoo) — same after-commit rule.
            from apps.integrations.models import CrmIntegration

            if CrmIntegration.all_objects.filter(company=company, is_enabled=True).exists():
                transaction.on_commit(partial(_enqueue_crm_dispatch, record.pk))

        # ── §5.4 success envelope, byte-compatible field set ────────────────
        return Response(
            {
                "success": True,
                "status": "received",
                "call_id": call_id,
                "server_id": _server_id(record),
                "received_at": record.received_at.astimezone(ZoneInfo("UTC")).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "resolved_name": resolved_name,
                "audio": audio_body,
            }
        )


class CallsListView(BaseApiView):
    """§6 — dedup pre-check before uploading."""

    throttle_scope = "calls_list"

    @extend_schema(
        request=CallsListRequestSerializer,
        responses={200: OpenApiResponse(description="§6 envelope")},
        summary="Check which call_ids already exist (contract §6)",
    )
    def post(self, request: Request) -> Response:
        operator = authenticate_device(request)
        serializer = CallsListRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call_ids: list[str] = serializer.validated_data["call_ids"]

        existing = {
            record.call_id: record
            for record in CallRecord.all_objects.filter(
                company=operator.company, call_id__in=call_ids
            )
        }
        calls: list[dict[str, Any]] = []
        for call_id in call_ids:
            record = existing.get(call_id)
            if record is not None:
                # server_id present ONLY when exists (§6 example).
                calls.append({"call_id": call_id, "exists": True, "server_id": _server_id(record)})
            else:
                calls.append({"call_id": call_id, "exists": False})
        return Response({"success": True, "calls": calls})


class StatsSummaryView(BaseApiView):
    """§7 — this operator's aggregate stats from the server's own data."""

    throttle_scope = "stats"

    @extend_schema(
        request=StatsRequestSerializer,
        responses={200: OpenApiResponse(description="§7 envelope")},
        summary="Operator stats summary (contract §7)",
    )
    def post(self, request: Request) -> Response:
        operator = authenticate_device(request)
        serializer = StatsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        aggregates = CallRecord.all_objects.filter(
            company=operator.company, operator=operator
        ).aggregate(
            total_duration_sec=Sum("duration"),
            total_count=Count("id"),
            inbound_count=Count("id", filter=Q(call_type=CallRecord.CallType.INBOUND)),
            outbound_count=Count("id", filter=Q(call_type=CallRecord.CallType.OUTBOUND)),
            missed_count=Count("id", filter=Q(call_status=CallRecord.CallStatus.NO_ANSWER)),
        )
        return Response(
            {
                "success": True,
                "total_duration_sec": aggregates["total_duration_sec"] or 0,
                "total_count": aggregates["total_count"],
                "inbound_count": aggregates["inbound_count"],
                "outbound_count": aggregates["outbound_count"],
                "missed_count": aggregates["missed_count"],
            }
        )


class LogView(BaseApiView):
    """§8 — device diagnostic log (NOT a call log)."""

    throttle_scope = "log"

    @extend_schema(
        request=LogRequestSerializer,
        responses={200: OpenApiResponse(description='{"success": true}')},
        summary="Upload device diagnostic log (contract §8)",
    )
    def post(self, request: Request) -> Response:
        operator = authenticate_device(request)
        serializer = LogRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        AppLog.all_objects.create(
            company=operator.company,
            operator=operator,
            hours=data["hours"],
            log_text=data["log_text"],
        )
        return Response({"success": True})
