"""Cabinet endpoints — /api/web/v1/settings/integrations (company admins)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from secrets import token_hex
from typing import Any, cast

from django.db.models import Count, Max
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import OperatorProfile, User
from apps.api.errors import ApiError, ErrorCode
from apps.companies.models import Company
from apps.core import netguard
from apps.core.models import AuditLog
from apps.core.phone import normalize_phone
from apps.web.permissions import AdminCabinetView, CabinetView

from . import kotib_analysis, providers
from .models import CallAnalysis, CrmCatalogEntry, CrmDelivery, CrmIntegration

logger = logging.getLogger(__name__)

DELIVERIES_PAGE = 50

# Kotib calls our public API back (account.info, users.list) *during* the
# connect request, so the candidate key must already authenticate by then.
KOTIB_PENDING_TTL = timedelta(minutes=5)

PROVIDERS = tuple(CrmIntegration.Provider.values)

# Customer-typed outbound address per provider (Kotib's base URL is ours).
URL_FIELDS = {"bitrix24": "webhook_url", "amocrm": "base_url", "odoo": "url"}

# Non-secret defaults shown in an empty form.
CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("base_url", "access_token", "responsible_user_id", "region"),
    # user_map: {"<OperatorProfile id>": "<Bitrix24 user id>"}; user_id = fallback.
    # + moizvonki-style card options (providers.B24_DEFAULTS).
    "bitrix24": (
        "webhook_url",
        "user_id",
        "account",
        "region",
        "user_map",
        "save_external_calls",
        "create_card",
        "lead_source",
        "only_answered",
    ),
    "odoo": ("url", "db", "login", "api_key"),
    # webhook_url / webhook_secret are stored too but NEVER leave the server.
    "kotib": (
        "api_key",
        "company_name",
        "employees_created",
        "employees_existing",
        "employees_created_inactive",
    ),
}


def _mask(value: str) -> str:
    value = str(value or "")
    if len(value) <= 10:
        return "•••" if value else ""
    return f"{value[:4]}…{value[-4:]}"


def _body(integration: CrmIntegration | None, provider: str) -> dict[str, Any]:
    config = dict(integration.config) if integration else {}
    secrets = providers.SECRET_FIELDS.get(provider, ())
    shown = {
        field: (_mask(config.get(field, "")) if field in secrets else config.get(field, ""))
        for field in CONFIG_FIELDS[provider]
    }
    if "user_map" in shown:
        shown["user_map"] = dict(config.get("user_map") or {})
    if provider == CrmIntegration.Provider.BITRIX24:
        shown.update(providers.b24_options(config))
        # Detected portal mode: "classic" (with leads) | "simple" (no leads) | "".
        shown["crm_mode"] = config.get("crm_mode") or ""
        shown["crm_mode_checked_at"] = config.get("crm_mode_checked_at")
        shown["crm_mode_assumed"] = bool(config.get("crm_mode_assumed"))
    if provider == CrmIntegration.Provider.KOTIB:
        shown.update(_kotib_analysis_fields(integration))
    return {
        "provider": provider,
        "is_enabled": bool(integration and integration.is_enabled),
        "configured": bool(integration and integration.config),
        "config": shown,
        "last_status": integration.last_status if integration else "",
        "last_error": integration.last_error if integration else "",
        "last_delivery_at": integration.last_delivery_at.isoformat()
        if integration and integration.last_delivery_at
        else None,
    }


def _kotib_analysis_fields(integration: CrmIntegration | None) -> dict[str, Any]:
    """Inbound AI-analysis webhook settings shown on the Kotib card. The URL
    (with its token) is meant for the admin to hand to Kotib; the secret is
    masked like every other secret."""
    config = integration.config if integration else {}
    token = str(config.get("analysis_token") or "")
    stats: dict[str, Any] = {"n": 0, "last": None}
    if integration is not None:
        stats = CallAnalysis.all_objects.filter(company_id=integration.company_id).aggregate(
            n=Count("id"), last=Max("updated_at")
        )
    return {
        "analysis_webhook_url": kotib_analysis.webhook_url(integration.company, token)
        if integration is not None and token
        else "",
        "analysis_secret": _mask(str(config.get("analysis_secret") or "")),
        "analysis_last_received_at": stats["last"].isoformat() if stats["last"] else None,
        "analysis_count": stats["n"],
    }


def _clean_user_map(raw: Any, company: Company) -> dict[str, str]:
    """Validate a Bitrix24 ``user_map``: keys are THIS company's operator ids,
    values positive integer strings; empty values are dropped."""
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ApiError(ErrorCode.MISSING_FIELD, "user_map must be an object", 400)
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        user = "" if value is None else str(value).strip()
        if not user:
            continue
        if not re.fullmatch(r"[1-9][0-9]{0,9}", user):
            raise ApiError(
                ErrorCode.MISSING_FIELD,
                f"user_map[{key}]: Bitrix24 user id must be a positive integer",
                400,
            )
        cleaned[str(key).strip()] = user
    ids = {k for k in cleaned if k.isdigit()}
    known = {
        str(pk)
        for pk in OperatorProfile.all_objects.filter(
            company=company, pk__in=[int(k) for k in ids]
        ).values_list("pk", flat=True)
    }
    if unknown := sorted(set(cleaned) - known):
        raise ApiError(
            ErrorCode.MISSING_FIELD, f"user_map: unknown operator id(s) {', '.join(unknown)}", 400
        )
    return cleaned


# True/False also match the ints 1/0.
_TRUE = {True, "1", "true", "yes", "on"}
_FALSE = {False, "0", "false", "no", "off"}


def _clean_b24_option(field: str, raw: Any) -> Any:
    """Validate one Bitrix24 card option (400 on a bad value)."""
    default = providers.B24_DEFAULTS[field]
    if isinstance(default, bool):
        value = raw.strip().lower() if isinstance(raw, str) else raw
        if not isinstance(value, bool | int | str):
            raise ApiError(ErrorCode.MISSING_FIELD, f"{field} must be true or false", 400)
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
        raise ApiError(ErrorCode.MISSING_FIELD, f"{field} must be true or false", 400)
    value = str(raw if raw is not None else "").strip()
    if field == "create_card":
        value = value.lower() or default
        if value not in providers.B24_CARD_MODES:
            modes = ", ".join(providers.B24_CARD_MODES)
            raise ApiError(ErrorCode.MISSING_FIELD, f"create_card must be one of: {modes}", 400)
        return value
    # lead_source: a Bitrix24 SOURCE status id (CALL, WEB, UC_ABC123, …).
    value = value.upper() or default
    if not re.fullmatch(r"[A-Z0-9_]{1,50}", value):
        raise ApiError(
            ErrorCode.MISSING_FIELD, "lead_source must be a Bitrix24 source id (A-Z, 0-9, _)", 400
        )
    return value


def _merge_config(
    provider: str,
    incoming: dict[str, Any],
    existing: dict[str, Any],
    company: Company | None = None,
) -> dict[str, Any]:
    """Masked secret values ("aBcD…wxyz") keep the previously stored secret."""
    merged = dict(existing)
    secrets = providers.SECRET_FIELDS.get(provider, ())
    for field in CONFIG_FIELDS[provider]:
        if field not in incoming:
            continue
        if field == "user_map":
            if company is None:  # pragma: no cover - always passed by the view
                raise ValueError("company required to validate user_map")
            merged[field] = _clean_user_map(incoming[field], company)
            continue
        if provider == CrmIntegration.Provider.BITRIX24 and field in providers.B24_DEFAULTS:
            merged[field] = _clean_b24_option(field, incoming[field])
            continue
        value = str(incoming.get(field) or "").strip()
        if field in secrets and ("…" in value or value == "•••"):
            continue  # unchanged masked echo from the form
        merged[field] = value
    return merged


class IntegrationsView(AdminCabinetView):
    @extend_schema(summary="All CRM integrations (secrets masked)")
    def get(self, request: Request) -> Response:
        rows = {i.provider: i for i in CrmIntegration.objects.all()}
        kotib = rows.get(CrmIntegration.Provider.KOTIB)
        if kotib is not None and kotib.is_enabled:
            kotib_analysis.ensure_token(kotib)  # rows connected before the AI webhook
        return Response(
            {
                "success": True,
                "integrations": [_body(rows.get(p), p) for p in PROVIDERS],
            }
        )


class IntegrationDetailView(AdminCabinetView):
    def _provider(self, provider: str) -> str:
        if provider not in PROVIDERS:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown provider {provider}", 404)
        return provider

    @extend_schema(summary="Save a CRM integration (enable requires valid config)")
    def put(self, request: Request, provider: str) -> Response:
        provider = self._provider(provider)
        integration = CrmIntegration.objects.filter(provider=provider).first()
        if provider == CrmIntegration.Provider.KOTIB:
            return self._put_kotib(request, integration)
        existing = dict(integration.config) if integration else {}
        config = _merge_config(
            provider, dict(request.data.get("config") or {}), existing, self.company
        )
        is_enabled = bool(request.data.get("is_enabled", integration.is_enabled if integration else False))
        # SSRF guard: the CRM address must be a public https host (checked
        # again right before every request).
        if url := str(config.get(URL_FIELDS.get(provider, "")) or "").strip():
            try:
                netguard.check_url(url)
            except netguard.UnsafeURL as exc:
                raise ApiError(
                    ErrorCode.MISSING_FIELD, f"CRM manzili rad etildi: {exc}", 400
                ) from None
        if is_enabled:
            try:
                providers.validate_config(provider, config)
            except providers.ProviderError as exc:
                raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
            if provider == CrmIntegration.Provider.BITRIX24:
                # Fresh portal mode (leads / simple CRM) on every save.
                providers.b24_refresh_mode(config, force=True)
        if integration is None:
            integration = CrmIntegration.all_objects.create(
                company=self.company, provider=provider, config=config, is_enabled=is_enabled
            )
        else:
            integration.config = config
            integration.is_enabled = is_enabled
            integration.save(update_fields=["config", "is_enabled", "updated_at"])
        AuditLog.objects.create(
            company=self.company,
            actor=cast(User, request.user),
            action="settings.integration_saved",
            target_model="integrations.CrmIntegration",
            target_id=str(integration.pk),
            changes={"provider": provider, "is_enabled": is_enabled},
        )
        return Response({"success": True, "integration": _body(integration, provider)})

    def _put_kotib(self, request: Request, integration: CrmIntegration | None) -> Response:
        """Kotib: saving = (re)connect on Kotib's side with a fresh webhook
        secret; the returned webhook URL + secret live only in this row's
        config (Company.webhook_url stays the customer's own webhook).

        Kotib reads our public API with its OWN key (``doocall_api_key``),
        never Company.api_key — wiping it on disconnect revokes access."""
        is_enabled = bool(
            request.data.get("is_enabled", integration.is_enabled if integration else False)
        )
        if not is_enabled:
            return self._disconnect(request, "kotib", integration)
        existing = dict(integration.config) if integration else {}
        incoming = str((request.data.get("config") or {}).get("api_key") or "").strip()
        masked_echo = "…" in incoming or incoming == "•••"
        api_key = incoming if incoming and not masked_echo else str(existing.get("api_key") or "")
        if not api_key:
            raise ApiError(ErrorCode.MISSING_FIELD, "missing fields: api_key", 400)

        company = self.company
        # Reuse Kotib's key on a plain re-save; a new Kotib key (possibly a
        # different Kotib company) gets a fresh one.
        doocall_api_key = str(existing.get("doocall_api_key") or "")
        if not doocall_api_key or api_key != existing.get("api_key"):
            doocall_api_key = uuid.uuid4().hex
        user = cast(User, request.user)
        user_name = user.email or user.username
        webhook_secret = token_hex(32)
        # Stage the candidate as a short-lived pending key (committed before
        # the HTTP call; no atomic block) so Kotib's call-back can use it. The
        # active key and is_enabled stay as they are until Kotib says yes.
        if integration is None:
            integration = CrmIntegration.all_objects.create(
                company=company, provider="kotib", config={}, is_enabled=False
            )
        integration.config = {
            **integration.config,
            "pending_doocall_api_key": doocall_api_key,
            "pending_doocall_api_key_until": (timezone.now() + KOTIB_PENDING_TTL).isoformat(),
        }
        integration.save(update_fields=["config", "updated_at"])
        try:
            result = providers.kotib_connect(
                api_key, company.slug, user_name, doocall_api_key, webhook_secret
            )
        except providers.ProviderError as exc:
            # Nothing is enabled; the pending key and new secret are dropped.
            integration.config = {
                k: v for k, v in integration.config.items() if not k.startswith("pending_")
            }
            integration.save(update_fields=["config", "updated_at"])
            raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None

        employees = result["employees"]
        config = {
            "api_key": api_key,
            "webhook_url": result["webhook_url"],
            "webhook_secret": webhook_secret,
            "doocall_api_key": doocall_api_key,
            # Inbound AI-analysis webhook: kept across re-saves.
            "analysis_token": existing.get("analysis_token") or kotib_analysis.new_token(),
            **(
                {"analysis_secret": existing["analysis_secret"]}
                if existing.get("analysis_secret")
                else {}
            ),
            "user_name": user_name,
            "company_name": result["company"],
            # null = Kotib could not list operators yet (connection still saved).
            **{
                f"employees_{key}": None if employees is None else employees.get(key)
                for key in ("created", "existing", "created_inactive")
            },
        }
        # Fresh config: the candidate becomes active, pending_* is dropped.
        integration.config = config
        integration.is_enabled = True
        integration.last_status = "ok"
        integration.last_error = ""
        integration.save(
            update_fields=["config", "is_enabled", "last_status", "last_error", "updated_at"]
        )
        AuditLog.objects.create(
            company=company,
            actor=user,
            action="settings.integration_saved",
            target_model="integrations.CrmIntegration",
            target_id=str(integration.pk),
            changes={"provider": "kotib", "is_enabled": True},
        )
        return Response({"success": True, "integration": _body(integration, "kotib")})

    @extend_schema(summary="Disconnect a CRM integration (disable + wipe credentials)")
    def delete(self, request: Request, provider: str) -> Response:
        """Hard disconnect: nothing is delivered to this CRM any more and the
        stored credentials are dropped. Dispatch only looks at ``is_enabled``
        rows, so flipping it off is what actually stops the traffic."""
        provider = self._provider(provider)
        integration = CrmIntegration.objects.filter(provider=provider).first()
        return self._disconnect(request, provider, integration)

    def _disconnect(
        self, request: Request, provider: str, integration: CrmIntegration | None
    ) -> Response:
        if integration is not None and provider == CrmIntegration.Provider.KOTIB:
            api_key = str(integration.config.get("api_key") or "")
            if api_key:
                try:
                    providers.kotib_disconnect(api_key, self.company.slug)
                except providers.ProviderError as exc:
                    # Best effort: wipe locally anyway; Kotib 410s the old URL
                    # once it is disconnected there.
                    logger.warning(
                        "kotib disconnect failed for company %s: %s", self.company.pk, exc
                    )
        if integration is not None:
            integration.is_enabled = False
            integration.config = {}
            integration.last_status = ""
            integration.last_error = ""
            integration.save(
                update_fields=["is_enabled", "config", "last_status", "last_error", "updated_at"]
            )
            AuditLog.objects.create(
                company=self.company,
                actor=cast(User, request.user),
                action="settings.integration_disconnected",
                target_model="integrations.CrmIntegration",
                target_id=str(integration.pk),
                changes={"provider": provider},
            )
        return Response({"success": True, "integration": _body(integration, provider)})


class CrmCatalogListView(CabinetView):
    @extend_schema(summary="Active CRM catalog tiles for the integration grid")
    def get(self, request: Request) -> Response:
        from .views_catalog import logo_public_url

        rows = [
            {
                "id": e.pk,
                "name": e.name,
                "site_url": e.site_url,
                "logo_url": logo_public_url(e),
            }
            for e in CrmCatalogEntry.objects.filter(is_active=True)
        ]
        return Response({"success": True, "entries": rows})


def _delivery_row(delivery: CrmDelivery) -> dict[str, Any]:
    call = delivery.call
    return {
        "id": delivery.pk,
        "call_id": call.pk,
        "counterparty_number": call.counterparty_number,
        "counterparty_name": call.resolved_name or call.counterparty_name,
        "direction": call.call_type,
        "call_status": call.call_status,
        "start_time": call.start_time.isoformat(),
        "status": delivery.status,
        "error": delivery.error,
        "is_retry": delivery.is_retry,
        "created_at": delivery.created_at.isoformat(),
    }


class IntegrationDeliveriesView(AdminCabinetView):
    @extend_schema(summary="Per-call delivery log for one CRM (?status=error&page=N)")
    def get(self, request: Request, provider: str) -> Response:
        if provider not in PROVIDERS:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown provider {provider}", 404)
        qs = CrmDelivery.objects.filter(provider=provider).select_related("call")
        status = request.query_params.get("status", "")
        if status in CrmDelivery.Status.values:
            qs = qs.filter(status=status)
        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        total = qs.count()
        offset = (page - 1) * DELIVERIES_PAGE
        rows = [_delivery_row(d) for d in qs[offset : offset + DELIVERIES_PAGE]]

        from django.utils import timezone

        since = timezone.now() - timezone.timedelta(days=30)
        recent = CrmDelivery.objects.filter(provider=provider, created_at__gte=since)
        return Response(
            {
                "success": True,
                "count": total,
                "page": page,
                "pages": max(1, -(-total // DELIVERIES_PAGE)),
                "summary": {
                    "ok_30d": recent.filter(status=CrmDelivery.Status.OK).count(),
                    "error_30d": recent.filter(status=CrmDelivery.Status.ERROR).count(),
                },
                "deliveries": rows,
            }
        )


class IntegrationRetryView(AdminCabinetView):
    @extend_schema(summary="Re-send one call to this CRM now (sync; writes a retry row)")
    def post(self, request: Request, provider: str, call_id: int) -> Response:
        from apps.calls.models import CallRecord

        from .tasks import deliver, public_record_url

        if provider not in PROVIDERS:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown provider {provider}", 404)
        integration = CrmIntegration.objects.filter(provider=provider).first()
        if integration is None or not integration.is_enabled or not integration.config:
            raise ApiError(ErrorCode.MISSING_FIELD, "integration not connected", 400)
        record = CallRecord.objects.filter(pk=call_id).first()
        if record is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "call not found", 404)
        delivery = deliver(integration, record, public_record_url(record), is_retry=True)
        # Always 200: the outcome (incl. the CRM's error text) is in the body,
        # so the UI can show it instead of a generic transport error.
        return Response(
            {
                "success": delivery.status == CrmDelivery.Status.OK,
                "error": delivery.error,
                "delivery": _delivery_row(delivery),
            }
        )


class IntegrationTestView(AdminCabinetView):
    @extend_schema(summary="Live connection test against the CRM")
    def post(self, request: Request, provider: str) -> Response:
        if provider not in PROVIDERS:
            raise ApiError(ErrorCode.MISSING_FIELD, f"unknown provider {provider}", 404)
        integration = CrmIntegration.objects.filter(provider=provider).first()
        if integration is None or not integration.config:
            raise ApiError(ErrorCode.MISSING_FIELD, "integration not configured", 400)
        try:
            detail = providers.test_connection(provider, integration.config, company=self.company)
        except providers.ProviderError as exc:
            integration.last_status = "error"
            integration.last_error = str(exc)[:500]
            integration.save(update_fields=["last_status", "last_error"])
            return Response({"success": False, "error": str(exc)[:500]}, status=502)
        integration.last_status = "ok"
        integration.last_error = ""
        update_fields = ["last_status", "last_error"]
        if provider == CrmIntegration.Provider.BITRIX24:
            providers.b24_refresh_mode(integration.config, force=True)
            update_fields.append("config")
        integration.save(update_fields=update_fields)
        return Response({"success": True, "detail": detail})


def _connected_kotib() -> CrmIntegration:
    integration = CrmIntegration.objects.filter(provider=CrmIntegration.Provider.KOTIB).first()
    if integration is None or not integration.is_enabled or not integration.config:
        raise ApiError(ErrorCode.MISSING_FIELD, "Kotib is not connected", 400)
    connected: CrmIntegration = integration
    return connected


class KotibAnalysisSecretView(AdminCabinetView):
    @extend_schema(summary="Save/replace the secret Kotib signs analysis webhooks with")
    def put(self, request: Request) -> Response:
        """Stored only on our side (Kotib connect is NOT called). Once set,
        unsigned or wrongly signed analysis messages are rejected (401)."""
        integration = _connected_kotib()
        secret = str(request.data.get("secret") or "").strip()
        if "…" in secret or secret == "•••":
            return Response({"success": True, "integration": _body(integration, "kotib")})
        if not secret or len(secret) > 256:
            raise ApiError(ErrorCode.MISSING_FIELD, "secret must be 1–256 characters", 400)
        kotib_analysis.ensure_token(integration)
        integration.config = {**integration.config, "analysis_secret": secret}
        integration.save(update_fields=["config", "updated_at"])
        AuditLog.objects.create(
            company=self.company,
            actor=cast(User, request.user),
            action="settings.kotib_analysis_secret_saved",
            target_model="integrations.CrmIntegration",
            target_id=str(integration.pk),
        )
        return Response({"success": True, "integration": _body(integration, "kotib")})


class KotibAnalysisRotateView(AdminCabinetView):
    @extend_schema(summary="New analysis webhook URL (old one stops working at once)")
    def post(self, request: Request) -> Response:
        integration = _connected_kotib()
        integration.config = {
            **integration.config,
            "analysis_token": kotib_analysis.new_token(),
        }
        integration.save(update_fields=["config", "updated_at"])
        AuditLog.objects.create(
            company=self.company,
            actor=cast(User, request.user),
            action="settings.kotib_analysis_url_rotated",
            target_model="integrations.CrmIntegration",
            target_id=str(integration.pk),
        )
        return Response({"success": True, "integration": _body(integration, "kotib")})


B24_SCOPE_ERROR = (
    "Bitrix24 vebhukida «user» (Foydalanuvchilar) ruxsati yo'q — vebhukka shu "
    "ruxsatni qo'shing yoki ID'larni qo'lda kiriting"
)
B24_PHONE_FIELDS = ("PERSONAL_MOBILE", "WORK_PHONE", "PERSONAL_PHONE")


def _name_key(*parts: Any) -> str:
    return " ".join(" ".join(str(p or "") for p in parts).lower().split())


def _unique_suggestions(candidates: dict[str, set[str]]) -> dict[str, str]:
    """operator → its single candidate, unless that Bitrix24 user is also the
    single candidate of another operator (ambiguous → skipped)."""
    single = {op: next(iter(ids)) for op, ids in candidates.items() if len(ids) == 1}
    claimed: dict[str, int] = {}
    for b24_id in single.values():
        claimed[b24_id] = claimed.get(b24_id, 0) + 1
    return {op: b24_id for op, b24_id in single.items() if claimed[b24_id] == 1}


def b24_suggestions(
    operators: list[dict[str, Any]], users: list[dict[str, Any]], phone_code: str
) -> dict[str, str]:
    """Phone match first (operator SIM numbers vs Bitrix24 phones), then an
    exact case-insensitive full-name match (NAME LAST_NAME either order).
    Only unambiguous pairs are suggested."""
    by_phone: dict[str, set[str]] = {}
    by_name: dict[str, set[str]] = {}
    for user in users:
        b24_id = str(user.get("ID") or "")
        if not b24_id:
            continue
        for field in B24_PHONE_FIELDS:
            if number := normalize_phone(str(user.get(field) or ""), phone_code):
                by_phone.setdefault(number, set()).add(b24_id)
        first, last = user.get("NAME"), user.get("LAST_NAME")
        for key in {_name_key(first, last), _name_key(last, first)}:
            if key:
                by_name.setdefault(key, set()).add(b24_id)

    phone_candidates: dict[str, set[str]] = {}
    for op in operators:
        ids: set[str] = set()
        for number in op["phones"]:
            ids |= by_phone.get(normalize_phone(number, phone_code), set())
        if ids:
            phone_candidates[str(op["id"])] = ids
    suggestions = _unique_suggestions(phone_candidates)

    used = set(suggestions.values())
    name_candidates = {
        str(op["id"]): by_name.get(_name_key(op["full_name"]), set()) - used
        for op in operators
        if str(op["id"]) not in phone_candidates and _name_key(op["full_name"])
    }
    suggestions.update(_unique_suggestions({k: v for k, v in name_candidates.items() if v}))
    return suggestions


def _b24_user_id(user: dict[str, Any]) -> str:
    value = user.get("ID")
    if isinstance(value, bool) or not isinstance(value, int | str):
        return ""
    return str(value) if re.fullmatch(r"[1-9][0-9]{0,9}", str(value)) else ""


def _b24_text(user: dict[str, Any], field: str) -> str:
    value = user.get(field)
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return ""
    return providers.safe_text(value)


class Bitrix24UsersView(AdminCabinetView):
    @extend_schema(summary="Bitrix24 users + DooCall operators + mapping suggestions")
    def get(self, request: Request) -> Response:
        integration = CrmIntegration.objects.filter(
            provider=CrmIntegration.Provider.BITRIX24
        ).first()
        if integration is None or not str(integration.config.get("webhook_url") or "").strip():
            raise ApiError(ErrorCode.MISSING_FIELD, "Bitrix24 is not configured", 400)
        operators = [
            {
                "id": op.pk,
                "full_name": op.full_name,
                "user_name": op.user_name,
                "phones": [sim.number for sim in op.sim_cards.all() if sim.number],
            }
            for op in OperatorProfile.objects.prefetch_related("sim_cards").order_by(
                "full_name", "user_name"
            )
        ]
        try:
            raw_users = providers.bitrix24_users(integration.config)
        except providers.ProviderError as exc:
            text = str(exc)
            if "insufficient_scope" not in text.lower():
                logger.warning("bitrix24 user.get failed for company %s: %s", self.company.pk, text)
            error = (
                B24_SCOPE_ERROR
                if "insufficient_scope" in text.lower() or "access_denied" in text.lower()
                else f"Bitrix24: {text[:300]}"
            )
            return Response({"success": False, "error": error, "operators": operators})
        # Only rows that look like Bitrix24 users, only parsed scalar fields.
        raw_users = [user for user in raw_users if _b24_user_id(user)]
        users = [
            {
                "id": _b24_user_id(user),
                "name": " ".join(
                    p for p in (_b24_text(user, "NAME"), _b24_text(user, "LAST_NAME")) if p
                )
                or _b24_text(user, "EMAIL"),
                "email": _b24_text(user, "EMAIL"),
                "phone": next(
                    (p for f in B24_PHONE_FIELDS if (p := _b24_text(user, f))),
                    "",
                ),
                "position": _b24_text(user, "WORK_POSITION"),
            }
            for user in raw_users
        ]
        return Response(
            {
                "success": True,
                "users": users,
                "operators": operators,
                "suggestions": b24_suggestions(operators, raw_users, self.company.phone_code),
            }
        )
