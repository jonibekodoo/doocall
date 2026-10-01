"""Cabinet endpoints — /api/web/v1/settings/integrations (company admins)."""

from __future__ import annotations

from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.api.errors import ApiError, ErrorCode
from apps.core.models import AuditLog
from apps.web.permissions import AdminCabinetView, CabinetView

from . import providers
from .models import CrmCatalogEntry, CrmDelivery, CrmIntegration

DELIVERIES_PAGE = 50

PROVIDERS = tuple(CrmIntegration.Provider.values)

# Non-secret defaults shown in an empty form.
CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("base_url", "access_token", "responsible_user_id", "region"),
    "bitrix24": ("webhook_url", "user_id", "account", "region"),
    "odoo": ("url", "db", "login", "api_key"),
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


def _merge_config(provider: str, incoming: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Masked secret values ("aBcD…wxyz") keep the previously stored secret."""
    merged = dict(existing)
    secrets = providers.SECRET_FIELDS.get(provider, ())
    for field in CONFIG_FIELDS[provider]:
        if field not in incoming:
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
        existing = dict(integration.config) if integration else {}
        config = _merge_config(provider, dict(request.data.get("config") or {}), existing)
        is_enabled = bool(request.data.get("is_enabled", integration.is_enabled if integration else False))
        if is_enabled:
            try:
                providers.validate_config(provider, config)
            except providers.ProviderError as exc:
                raise ApiError(ErrorCode.MISSING_FIELD, str(exc), 400) from None
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

    @extend_schema(summary="Disconnect a CRM integration (disable + wipe credentials)")
    def delete(self, request: Request, provider: str) -> Response:
        """Hard disconnect: nothing is delivered to this CRM any more and the
        stored credentials are dropped. Dispatch only looks at ``is_enabled``
        rows, so flipping it off is what actually stops the traffic."""
        provider = self._provider(provider)
        integration = CrmIntegration.objects.filter(provider=provider).first()
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
            detail = providers.test_connection(provider, integration.config)
        except providers.ProviderError as exc:
            integration.last_status = "error"
            integration.last_error = str(exc)[:500]
            integration.save(update_fields=["last_status", "last_error"])
            return Response({"success": False, "error": str(exc)[:500]}, status=502)
        integration.last_status = "ok"
        integration.last_error = ""
        integration.save(update_fields=["last_status", "last_error"])
        return Response({"success": True, "detail": detail})
