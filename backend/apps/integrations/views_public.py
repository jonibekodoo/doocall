"""Public integration surface (moizvonki-style).

* ``POST /api/v1`` — single action endpoint for third-party systems.
  Auth rides in the JSON body: ``user_name`` (cabinet user e-mail) +
  ``api_key`` (the company API key from Settings → Integration, or the
  per-integration read-only key issued to Kotib Analytics on connect).
* ``GET /api/public/rec/<server_id>?sig=…`` — permanent recording link
  (302 → fresh presigned MinIO URL) safe to store inside a CRM.
* ``GET /api/public/crm-logo/<id>`` — catalog tile logo (302 → MinIO).
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
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

from .models import CrmCatalogEntry, CrmIntegration
from .providers import KOTIB_ALLOWED_ACTIONS
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


def _same_key(stored: Any, api_key: str) -> bool:
    stored = str(stored or "")
    return bool(stored) and hmac.compare_digest(stored.encode(), api_key.encode())


def _kotib_company(api_key: str) -> Company | None:
    """Company of the Kotib integration holding this key: the active key of an
    ENABLED integration, or the not-yet-expired pending key staged while
    connect is in flight (Kotib verifies it via account.info/users.list)."""
    integration = (
        CrmIntegration.all_objects.filter(provider=CrmIntegration.Provider.KOTIB)
        .filter(
            Q(is_enabled=True, config__doocall_api_key=api_key)
            | Q(config__pending_doocall_api_key=api_key)
        )
        .select_related("company")
        .first()
    )
    if integration is None:
        return None
    config = integration.config
    company: Company = integration.company
    if integration.is_enabled and _same_key(config.get("doocall_api_key"), api_key):
        return company
    until = parse_datetime(str(config.get("pending_doocall_api_key_until") or ""))
    if (
        until is not None
        and timezone.now() < until
        and _same_key(config.get("pending_doocall_api_key"), api_key)
    ):
        return company
    return None


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
        # Kotib's own key: valid only while that integration is enabled.
        allowed_actions: frozenset[str] | None = None
        if company is None:
            company = _kotib_company(api_key)
            allowed_actions = KOTIB_ALLOWED_ACTIONS
        if company is None:
            raise ApiError(ErrorCode.INVALID_API_KEY, "invalid api_key", http.HTTP_401_UNAUTHORIZED)
        member = (
            User.objects.filter(company=company).filter(username__iexact=user_name).first()
            or User.objects.filter(company=company, email__iexact=user_name).first()
        )
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
        if allowed_actions is not None and action not in allowed_actions:
            raise ApiError(
                ErrorCode.INVALID_API_KEY,
                f"action {action!r} is not allowed for this api_key",
                http.HTTP_403_FORBIDDEN,
            )
        self._member = member  # the API user (created_by of remote dials)
        handler = {
            "calls.list": self._calls_list,
            "calls.get": self._calls_get,
            "users.list": self._users_list,
            "account.info": self._account_info,
            # Remote Dial (company opt-in; never for the Kotib read-only key).
            "calls.dial": self._calls_dial,
            "calls.dial.status": self._calls_dial_status,
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
            raise ApiError(ErrorCode.MISSING_FIELD, "offset/limit must be integers", 400) from None
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

    def _dial_enabled(self, company: Company) -> None:
        if not (company.feature_flags or {}).get("api_dial_enabled", False):
            raise ApiError(
                "feature_disabled",
                "remote dial via the API is not enabled for this account",
                http.HTTP_403_FORBIDDEN,
            )

    def _calls_dial(self, company: Company, data: dict[str, Any]) -> Response:
        """{operator: <user_name>, number, device_id?} → the operator's phone
        dials (same validation, allowlist, rate limits, audit as the cabinet)."""
        from apps.dial import services as dial

        self._dial_enabled(company)
        operator = OperatorProfile.all_objects.filter(
            company=company, user_name=str(data.get("operator") or "").strip(), is_active=True
        ).first()
        if operator is None:
            raise ApiError("operator_not_found", "operator not found", http.HTTP_404_NOT_FOUND)
        try:
            command = dial.dial_operator(
                company=company,
                operator=operator,
                user=self._member,
                raw_number=data.get("number"),
                raw_device_id=data.get("device_id") or "",
                source="api",
            )
        except dial.DialError as exc:
            return Response(
                {"success": False, "error_code": exc.code, "message": exc.message},
                status=exc.status,
            )
        if command.status == command.Status.OFFLINE:
            return Response(
                {
                    "success": False,
                    "error_code": "device_offline",
                    "command_id": str(command.pk),
                    "status": "offline",
                },
                status=http.HTTP_409_CONFLICT,
            )
        return Response({"success": True, "command_id": str(command.pk), "status": command.status})

    def _calls_dial_status(self, company: Company, data: dict[str, Any]) -> Response:
        import uuid

        from apps.dial import services as dial
        from apps.dial.models import DialCommand
        from apps.dial.views import command_body

        self._dial_enabled(company)
        try:
            command_id = uuid.UUID(str(data.get("command_id") or ""))
        except ValueError:
            raise ApiError(
                ErrorCode.MISSING_FIELD, "command_id must be a UUID", http.HTTP_400_BAD_REQUEST
            ) from None
        dial.expire_stale(company.pk)
        command = (
            DialCommand.all_objects.select_related("operator")
            .filter(company=company, pk=command_id)
            .first()
        )
        if command is None:
            raise ApiError("not_found", "command not found", http.HTTP_404_NOT_FOUND)
        return Response({"success": True, "command": command_body(command)})

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
        audio = record.audios.filter(kind=CallAudio.Kind.PRIMARY).first() or record.audios.first()
        if audio is None:
            return HttpResponse(status=404)
        return HttpResponseRedirect(storage.presigned_url(audio.object_key))


LOGO_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}


class CrmLogoView(View):
    """Streams the logo bytes directly (no presigned redirect): browser
    privacy extensions were blocking the signed files.* redirect hop."""

    def get(self, request: HttpRequest, entry_id: int) -> HttpResponse:
        from django.conf import settings as dj_settings

        entry = CrmCatalogEntry.objects.filter(pk=entry_id, is_active=True).first()
        if entry is None or not entry.logo_key:
            return HttpResponse(status=404)
        try:
            obj = storage.client().get_object(dj_settings.MINIO_BUCKET, entry.logo_key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
        except Exception:  # noqa: BLE001 - missing object → plain 404
            return HttpResponse(status=404)
        ext = entry.logo_key.rsplit(".", 1)[-1].lower()
        response = HttpResponse(
            payload, content_type=LOGO_TYPES.get(ext, "application/octet-stream")
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class IntegratorLogoView(View):
    """Streams an integrator's logo bytes (mirrors CrmLogoView)."""

    def get(self, request: HttpRequest, integrator_id: int) -> HttpResponse:
        from django.conf import settings as dj_settings

        from apps.partners.models import Integrator

        integrator = Integrator.objects.filter(pk=integrator_id).first()
        if integrator is None or not integrator.logo_key:
            return HttpResponse(status=404)
        try:
            obj = storage.client().get_object(dj_settings.MINIO_BUCKET, integrator.logo_key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
        except Exception:  # noqa: BLE001 - missing object → plain 404
            return HttpResponse(status=404)
        ext = integrator.logo_key.rsplit(".", 1)[-1].lower()
        response = HttpResponse(
            payload, content_type=LOGO_TYPES.get(ext, "application/octet-stream")
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class SalesLogoView(View):
    """Streams a sales manager's logo bytes (mirrors IntegratorLogoView)."""

    def get(self, request: HttpRequest, manager_id: int) -> HttpResponse:
        from django.conf import settings as dj_settings

        from apps.partners.models import SalesManager

        manager = SalesManager.objects.filter(pk=manager_id).first()
        if manager is None or not manager.logo_key:
            return HttpResponse(status=404)
        try:
            obj = storage.client().get_object(dj_settings.MINIO_BUCKET, manager.logo_key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
        except Exception:  # noqa: BLE001
            return HttpResponse(status=404)
        ext = manager.logo_key.rsplit(".", 1)[-1].lower()
        response = HttpResponse(
            payload, content_type=LOGO_TYPES.get(ext, "application/octet-stream")
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class ProviderLogoView(View):
    """Streams a payment provider's logo bytes (mirrors IntegratorLogoView)."""

    def get(self, request: HttpRequest, provider: str) -> HttpResponse:
        from django.conf import settings as dj_settings

        from apps.billing.models import PaymentProviderConfig

        cfg = PaymentProviderConfig.objects.filter(provider=provider).first()
        if cfg is None or not cfg.logo_key:
            return HttpResponse(status=404)
        try:
            obj = storage.client().get_object(dj_settings.MINIO_BUCKET, cfg.logo_key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
        except Exception:  # noqa: BLE001
            return HttpResponse(status=404)
        ext = cfg.logo_key.rsplit(".", 1)[-1].lower()
        response = HttpResponse(
            payload, content_type=LOGO_TYPES.get(ext, "application/octet-stream")
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class OdooAppDownloadView(View):
    """Zips the bundled DooCall Odoo 19 addon on the fly (no auth —
    the module contains no secrets, only client-side code)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        import io as _io
        import zipfile
        from pathlib import Path

        from django.conf import settings as dj_settings

        app_dir = Path(dj_settings.BASE_DIR) / "odoo_app" / "doocall"
        if not app_dir.is_dir():
            return HttpResponse(status=404)
        buffer = _io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app_dir.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, "doocall/" + str(path.relative_to(app_dir)))
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="doocall_odoo19.zip"'
        return response


class PublicCrmCatalogView(View):
    """Active catalog tiles for the landing page (no auth)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.http import JsonResponse

        from .views_catalog import logo_public_url

        entries = [
            {
                "id": e.pk,
                "name": e.name,
                "site_url": e.site_url,
                "logo_url": logo_public_url(e),
            }
            for e in CrmCatalogEntry.objects.filter(is_active=True)
        ]
        return JsonResponse({"success": True, "entries": entries})


@method_decorator(csrf_exempt, name="dispatch")
class KotibAnalysisWebhookView(View):
    """``POST /api/public/kotib/analysis/<token>`` — Kotib pushes one
    ``analysis.completed`` message per analysed call. Fast DB-only work (Kotib
    waits ≤10 s, then retries); the same call may arrive again (latest wins).

    404 unknown token · 410 integration disabled · 401 bad/missing signature
    (once a secret is saved) · 413 body > 2 MB · 400 malformed · 200 stored or
    ignored (other events)."""

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        from django.core.exceptions import RequestDataTooBig
        from django.db import IntegrityError, transaction

        from . import kotib_analysis as ka

        def reply(code: int, **body: Any) -> JsonResponse:
            return JsonResponse({"success": code == 200, **body}, status=code)

        integration = ka.find_integration(token)
        if integration is None:
            return reply(404, message="unknown endpoint")
        company = integration.company
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and sub != company.slug:
            return reply(404, message="unknown endpoint")
        if not integration.is_enabled:
            return reply(410, message="integration disabled")

        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > ka.MAX_BODY_BYTES:
            return reply(413, message="body too large")
        try:
            raw = request.body
        except RequestDataTooBig:
            return reply(413, message="body too large")
        if len(raw) > ka.MAX_BODY_BYTES:
            return reply(413, message="body too large")

        secret = str(integration.config.get("analysis_secret") or "")
        if secret and not ka.signature_ok(
            secret, raw, request.headers.get("X-Kotib-Signature", "")
        ):
            return reply(401, message="invalid signature")

        try:
            payload = json.loads(raw)
        except ValueError:
            return reply(400, message="invalid JSON")
        if not isinstance(payload, dict):
            return reply(400, message="invalid JSON")
        if payload.get("event") != ka.EVENT:
            return reply(200, status="ignored")

        for attempt in range(2):  # a concurrent duplicate may win the insert
            try:
                with transaction.atomic():
                    analysis = ka.store(company, payload, verified=bool(secret))
                break
            except ka.PayloadError as exc:
                return reply(400, message=str(exc))
            except IntegrityError:
                if attempt:
                    raise
        return reply(200, status="stored", matched=analysis.call_id is not None)


def _b24_event_fields(request: HttpRequest) -> dict[str, str]:
    """Flatten Bitrix24's event POST: form keys like ``data[PHONE_NUMBER]``
    (what Bitrix sends) or a JSON body with nested data/auth objects."""
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            return {}
        flat: dict[str, str] = {}
        if isinstance(body, dict):
            for key, value in body.items():
                if isinstance(value, dict):
                    flat.update({f"{key}[{k}]": str(v) for k, v in value.items()})
                else:
                    flat[str(key)] = str(value)
        return flat
    return {key: request.POST.get(key, "") for key in request.POST}


@method_decorator(csrf_exempt, name="dispatch")
class Bitrix24ClickToCallView(View):
    """``POST /api/public/bitrix24/click-to-call/<token>`` — Bitrix24's
    outgoing webhook for ONEXTERNALCALLSTART (a user clicked a phone number
    in the CRM). The Bitrix user is mapped to a DooCall operator (user_map)
    and that operator's phone dials through Remote Dial. Always a quick 200
    once the token is valid; Bitrix may resend — one dial per CALL_ID."""

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        import logging

        from django.core.cache import cache

        from apps.dial import services as dial
        from apps.dial.models import DialCommand

        log = logging.getLogger("apps.integrations.click_to_call")

        def reply(code: int = 200, **body: Any) -> JsonResponse:
            return JsonResponse({"success": code == 200, **body}, status=code)

        integration = _b24_click_to_call_integration(token)
        if integration is None:
            return reply(404, message="unknown endpoint")
        company = integration.company
        sub = domains.company_subdomain(request.get_host())
        if sub is not None and sub != company.slug:
            return reply(404, message="unknown endpoint")
        fields = _b24_event_fields(request)
        # Signed by Bitrix24 or nothing: a missing stored token is a 401 too.
        expected = str(integration.config.get("b24_app_token") or "")
        given = fields.get("auth[application_token]", "")
        if not expected or not hmac.compare_digest(expected.encode(), given.encode()):
            return reply(401, message="invalid application_token")
        if not integration.is_enabled or not integration.config.get("click_to_call_enabled"):
            return reply(status="ignored", reason="disabled")
        if fields.get("event", "").upper() != "ONEXTERNALCALLSTART":
            return reply(status="ignored", reason="event")

        call_id = fields.get("data[CALL_ID]", "").strip()[:64]
        b24_user = fields.get("data[USER_ID]", "").strip()
        number = fields.get("data[PHONE_NUMBER_INTERNATIONAL]") or fields.get(
            "data[PHONE_NUMBER]", ""
        )
        if not call_id:
            return reply(status="ignored", reason="no_call_id")
        # Bitrix may resend the event: one dial per CALL_ID.
        if DialCommand.all_objects.filter(
            company=company, b24_call_id=call_id
        ).exists() or not cache.add(f"dial:b24:{company.pk}:{call_id}", 1, 600):
            return reply(status="duplicate")

        mapped = [
            int(op_id)
            for op_id, b24_id in (integration.config.get("user_map") or {}).items()
            if str(b24_id) == b24_user and str(op_id).isdigit()
        ]
        operators = list(
            OperatorProfile.all_objects.filter(company=company, pk__in=mapped, is_active=True)
        )
        if not operators:
            log.info(
                "bitrix24 click-to-call company=%s call=%s ignored=unmapped_user",
                company.pk,
                call_id,
            )
            return reply(status="ignored", reason="unmapped_user")
        # Several operators mapped to one Bitrix user: prefer one that is online.
        operators.sort(key=lambda op: not _has_online_device(company.pk, op))
        try:
            command = dial.dial_operator(
                company=company,
                operator=operators[0],
                user=None,
                raw_number=number,
                requester="Bitrix24",
                source="bitrix24",
                b24={
                    "call_id": call_id,
                    "user_id": b24_user,
                    "entity_type": fields.get("data[CRM_ENTITY_TYPE]", ""),
                    "entity_id": fields.get("data[CRM_ENTITY_ID]", ""),
                },
            )
        except dial.DialError as exc:
            log.info(
                "bitrix24 click-to-call company=%s call=%s refused=%s",
                company.pk,
                call_id,
                exc.code,
            )
            return reply(status="refused", error_code=exc.code)
        log.info(
            "bitrix24 click-to-call company=%s call=%s command=%s status=%s",
            company.pk,
            call_id,
            command.pk,
            command.status,
        )
        return reply(status=command.status, command_id=str(command.pk))


def _has_online_device(company_id: int, operator: OperatorProfile) -> bool:
    from apps.accounts.models import Device
    from apps.dial import services as dial

    for device_id in Device.all_objects.filter(operator=operator).values_list(
        "device_id", flat=True
    ):
        marker = dial.online(company_id, dial.clean_device_id(device_id))
        if marker and marker.get("operator_id") == operator.pk:
            return True
    return False


def _b24_click_to_call_integration(token: str) -> CrmIntegration | None:
    """Bitrix24 integration owning this click-to-call token (constant time)."""
    if not token:
        return None
    integration: CrmIntegration | None = (
        CrmIntegration.all_objects.filter(
            provider=CrmIntegration.Provider.BITRIX24, config__c2c_token=token
        )
        .select_related("company")
        .first()
    )
    if integration is None:
        return None
    stored = str(integration.config.get("c2c_token") or "")
    if not stored or not hmac.compare_digest(stored.encode(), token.encode()):
        return None
    return integration
