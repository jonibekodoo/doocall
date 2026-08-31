"""§6.5 Settings — groups, users, devices, toggles, api-key, webhook, license."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import Device, OperatorGroup, OperatorProfile, SimCard, User
from apps.api.errors import ApiError, ErrorCode
from apps.billing import services as billing
from apps.billing.models import Payment, Subscription
from apps.core.models import AuditLog
from apps.core.phone import normalize_phone

from .permissions import AdminCabinetView, CabinetView
from .tasks import deliver_webhook

ONLINE_WINDOW = timedelta(minutes=5)

ACCOUNT_FLAGS = ("contact_import_enabled", "recording_enabled", "pin_enabled")
ACCOUNT_FLAG_DEFAULTS = {
    "contact_import_enabled": True,
    "recording_enabled": True,
    "pin_enabled": False,
}


# ── Groups ─────────────────────────────────────────────────────────────────
class GroupsView(CabinetView):
    @extend_schema(summary="List groups")
    def get(self, request: Request) -> Response:
        rows = list(OperatorGroup.objects.values("id", "name").order_by("name"))
        return Response({"success": True, "groups": rows})

    @extend_schema(summary="Create group")
    def post(self, request: Request) -> Response:
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
        if OperatorGroup.objects.filter(name=name).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "group already exists", 400)
        group = OperatorGroup.all_objects.create(company=self.company, name=name)
        return Response(
            {"success": True, "group": {"id": group.pk, "name": group.name}},
            status=http.HTTP_201_CREATED,
        )


class GroupDetailView(CabinetView):
    def _get(self, group_id: int) -> OperatorGroup:
        group: OperatorGroup | None = OperatorGroup.objects.filter(pk=group_id).first()
        if group is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "group not found", 404)
        return group

    @extend_schema(summary="Rename group")
    def put(self, request: Request, group_id: int) -> Response:
        group = self._get(group_id)
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ApiError(ErrorCode.MISSING_FIELD, "name required", 400)
        group.name = name
        group.save(update_fields=["name"])
        return Response({"success": True})

    @extend_schema(summary="Delete group")
    def delete(self, request: Request, group_id: int) -> Response:
        self._get(group_id).delete()
        return Response({"success": True})


# ── Users / operators ──────────────────────────────────────────────────────
def operator_body(profile: OperatorProfile) -> dict[str, Any]:
    return {
        "id": profile.pk,
        "user_id": profile.user_id,
        "user_name": profile.user_name,
        "full_name": profile.full_name,
        "group_id": profile.group_id,
        "is_active": profile.is_active,
        "email": profile.user.email,
        "is_company_admin": profile.user.is_company_admin,
        "phones": [
            {"sim_slot": sim.sim_slot, "number": sim.number}
            for sim in profile.sim_cards.order_by("sim_slot")
        ],
    }


class UsersView(CabinetView):
    @extend_schema(summary="List company users/operators")
    def get(self, request: Request) -> Response:
        operators = OperatorProfile.objects.select_related("user").order_by("user_name")
        admins = list(
            User.tenant_objects.filter(operator_profile__isnull=True).values(
                "id", "email", "is_company_admin", "is_active"
            )
        )
        return Response(
            {
                "success": True,
                "operators": [operator_body(p) for p in operators],
                "web_users": admins,
            }
        )

    @extend_schema(summary="Create operator — returns mobile credentials ONCE")
    def post(self, request: Request) -> Response:
        user_name = (request.data.get("user_name") or "").strip()
        full_name = (request.data.get("full_name") or "").strip()
        phone = (request.data.get("phone") or "").strip()
        phone2 = (request.data.get("phone2") or "").strip()
        if not user_name:
            raise ApiError(ErrorCode.MISSING_FIELD, "user_name required", 400)
        if OperatorProfile.objects.filter(user_name=user_name).exists():
            raise ApiError(ErrorCode.MISSING_FIELD, "user_name already taken", 400)

        group = None
        if group_id := request.data.get("group_id"):
            group = OperatorGroup.objects.filter(pk=group_id).first()

        password = secrets.token_urlsafe(9)
        with transaction.atomic():
            user = User.objects.create_user(
                username=f"{user_name}@{self.company.slug}",
                password=password,
                company=self.company,
                first_name=full_name.split()[0] if full_name else "",
            )
            profile = OperatorProfile.all_objects.create(
                company=self.company,
                user=user,
                user_name=user_name,
                full_name=full_name,
                group=group,
            )
            # Operator's real SIM numbers — call attribution matches on them.
            for slot, number in ((0, phone), (1, phone2)):
                if number:
                    SimCard.all_objects.create(
                        company=self.company,
                        operator=profile,
                        sim_slot=slot,
                        number=normalize_phone(number),
                    )
            AuditLog.objects.create(
                company=self.company,
                actor=cast(User, request.user),
                action="settings.operator_created",
                target_model="accounts.OperatorProfile",
                target_id=str(profile.pk),
            )
        return Response(
            {
                "success": True,
                "operator": operator_body(profile),
                # Mobile credentials — shown exactly once, not retrievable later.
                "credentials": {
                    "user_name": user_name,
                    "password": password,
                    "api_key": profile.api_key,
                },
            },
            status=http.HTTP_201_CREATED,
        )


class UserDetailView(AdminCabinetView):
    def _get(self, operator_id: int) -> OperatorProfile:
        profile: OperatorProfile | None = (
            OperatorProfile.objects.select_related("user").filter(pk=operator_id).first()
        )
        if profile is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "operator not found", 404)
        return profile

    @extend_schema(summary="Update operator (incl. deactivate toggle → seats)")
    def patch(self, request: Request, operator_id: int) -> Response:
        profile = self._get(operator_id)
        if "full_name" in request.data:
            profile.full_name = request.data.get("full_name") or ""
        if "group_id" in request.data:
            profile.group = OperatorGroup.objects.filter(pk=request.data.get("group_id")).first()
        if "is_active" in request.data:
            # Billable seats react IMMEDIATELY (license endpoint reads live count).
            profile.is_active = bool(request.data["is_active"])
            profile.user.is_active = profile.is_active
            profile.user.save(update_fields=["is_active"])
            AuditLog.objects.create(
                company=self.company,
                actor=cast(User, request.user),
                action="settings.operator_toggled",
                target_model="accounts.OperatorProfile",
                target_id=str(profile.pk),
                changes={"is_active": profile.is_active},
            )
        profile.save()
        return Response({"success": True, "operator": operator_body(profile)})

    @extend_schema(summary="Delete operator")
    def delete(self, request: Request, operator_id: int) -> Response:
        profile = self._get(operator_id)
        profile.user.delete()  # cascades to profile
        return Response({"success": True})


class OperatorKeyRotateView(AdminCabinetView):
    @extend_schema(summary="Rotate an operator's mobile api_key (returned once)")
    def post(self, request: Request, operator_id: int) -> Response:
        profile = OperatorProfile.objects.filter(pk=operator_id).first()
        if profile is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "operator not found", 404)
        profile.api_key = uuid.uuid4().hex
        profile.save(update_fields=["api_key"])
        AuditLog.objects.create(
            company=self.company,
            actor=cast(User, request.user),
            action="settings.operator_key_rotated",
            target_model="accounts.OperatorProfile",
            target_id=str(profile.pk),
        )
        return Response({"success": True, "api_key": profile.api_key})


# ── Devices ────────────────────────────────────────────────────────────────
class DevicesView(CabinetView):
    @extend_schema(summary="Devices with SIMs, recording toggles, online status")
    def get(self, request: Request) -> Response:
        now = timezone.now()
        devices = Device.objects.select_related("operator").prefetch_related("operator__sim_cards")
        rows = []
        for device in devices:
            rows.append(
                {
                    "id": device.pk,
                    "operator_id": device.operator_id,
                    "operator": device.operator.user_name,
                    "device_id": device.device_id,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "app_version": device.app_version,
                    "os_version": device.os_version,
                    "last_seen_at": device.last_seen_at.isoformat()
                    if device.last_seen_at
                    else None,
                    "online": bool(
                        device.last_seen_at and now - device.last_seen_at < ONLINE_WINDOW
                    ),
                    "sims": [
                        {
                            "id": sim.pk,
                            "sim_slot": sim.sim_slot,
                            "number": sim.number,
                            "recording_enabled": sim.recording_enabled,
                        }
                        for sim in device.operator.sim_cards.all()
                    ],
                }
            )
        return Response({"success": True, "devices": rows})


class SimCardView(AdminCabinetView):
    @extend_schema(summary="Per-SIM: recording toggle / set phone number")
    def patch(self, request: Request, sim_id: int) -> Response:
        sim = SimCard.objects.filter(pk=sim_id).first()
        if sim is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "sim not found", 404)
        if "recording_enabled" in request.data:
            sim.recording_enabled = bool(request.data["recording_enabled"])
        if number := request.data.get("number"):
            sim.number = normalize_phone(number)
        sim.save()
        return Response(
            {
                "success": True,
                "sim": {
                    "id": sim.pk,
                    "sim_slot": sim.sim_slot,
                    "number": sim.number,
                    "recording_enabled": sim.recording_enabled,
                },
            }
        )


class DeviceDeleteView(AdminCabinetView):
    @extend_schema(summary="Delete device")
    def delete(self, request: Request, device_id: int) -> Response:
        deleted, _ = Device.objects.filter(pk=device_id).delete()
        if not deleted:
            raise ApiError(ErrorCode.MISSING_FIELD, "device not found", 404)
        return Response({"success": True})


# ── Account-wide toggles ───────────────────────────────────────────────────
class AccountSettingsView(AdminCabinetView):
    @extend_schema(summary="Account-wide toggles (contact import / recording / PIN)")
    def get(self, request: Request) -> Response:
        flags = {**ACCOUNT_FLAG_DEFAULTS, **(self.company.feature_flags or {})}
        return Response({"success": True, "settings": {k: flags[k] for k in ACCOUNT_FLAGS}})

    @extend_schema(summary="Update account-wide toggles")
    def put(self, request: Request) -> Response:
        company = self.company
        flags = {**ACCOUNT_FLAG_DEFAULTS, **(company.feature_flags or {})}
        for key in ACCOUNT_FLAGS:
            if key in request.data:
                flags[key] = bool(request.data[key])
        company.feature_flags = flags
        company.save(update_fields=["feature_flags", "updated_at"])
        return Response({"success": True, "settings": {k: flags[k] for k in ACCOUNT_FLAGS}})


# ── Company API key ────────────────────────────────────────────────────────
class ApiKeyView(AdminCabinetView):
    @extend_schema(summary="Show whether a company API key exists (masked)")
    def get(self, request: Request) -> Response:
        key = self.company.api_key
        return Response({"success": True, "api_key_masked": f"{key[:6]}…" if key else None})

    @extend_schema(summary="Generate/rotate the company API key (returned once)")
    def post(self, request: Request) -> Response:
        company = self.company
        company.api_key = uuid.uuid4().hex
        company.save(update_fields=["api_key", "updated_at"])
        AuditLog.objects.create(
            company=company,
            actor=cast(User, request.user),
            action="settings.api_key_rotated",
        )
        return Response({"success": True, "api_key": company.api_key})


# ── Webhook config ─────────────────────────────────────────────────────────
class WebhookSettingsView(AdminCabinetView):
    @extend_schema(summary="Get webhook config (secret masked)")
    def get(self, request: Request) -> Response:
        company = self.company
        return Response(
            {
                "success": True,
                "webhook_url": company.webhook_url or None,
                "secret_set": bool(company.webhook_secret),
            }
        )

    @extend_schema(summary="Set webhook URL (secret generated on first set)")
    def put(self, request: Request) -> Response:
        company = self.company
        url = (request.data.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            raise ApiError(ErrorCode.MISSING_FIELD, "url must be http(s)", 400)
        company.webhook_url = url
        secret_created = False
        if url and not company.webhook_secret:
            company.webhook_secret = secrets.token_hex(32)
            secret_created = True
        company.save(update_fields=["webhook_url", "webhook_secret", "updated_at"])
        return Response(
            {
                "success": True,
                "webhook_url": url or None,
                # Shown once when first generated so the receiver can verify HMAC.
                "secret": company.webhook_secret if secret_created else None,
            }
        )


class WebhookTestView(AdminCabinetView):
    @extend_schema(summary="Send a signed test delivery to the configured URL")
    def post(self, request: Request) -> Response:
        company = self.company
        if not company.webhook_url:
            raise ApiError(ErrorCode.MISSING_FIELD, "webhook URL not configured", 400)
        payload = {
            "event": "test",
            "company": company.slug,
            "sent_at": timezone.now().isoformat(),
        }
        try:
            status_code = deliver_webhook(company, payload)
        except Exception as exc:  # noqa: BLE001 - surface delivery failure to the UI
            return Response({"success": False, "error": str(exc)[:500]}, status=502)
        return Response({"success": True, "delivery_status": status_code})


# ── License ────────────────────────────────────────────────────────────────
class LicenseView(CabinetView):
    @extend_schema(summary="License state: trial/period, seats × price, payments")
    def get(self, request: Request) -> Response:
        company = self.company
        subscription = Subscription.all_objects.filter(company=company).first()
        seats = billing.seat_count(company)  # live — reacts to deactivation instantly
        price = (
            subscription.price_per_operator_uzs
            if subscription
            else billing.effective_price(company)
        )
        payments = [
            {
                "id": p.pk,
                "provider": p.provider,
                "amount_uzs": p.amount_uzs,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p in Payment.objects.order_by("-created_at")[:20]
        ]
        trial_days_left = None
        if company.status == "trial" and company.trial_ends_at:
            trial_days_left = max(0, (company.trial_ends_at - timezone.now()).days)
        return Response(
            {
                "success": True,
                "status": subscription.status if subscription else company.status,
                "trial_ends_at": company.trial_ends_at.isoformat()
                if company.trial_ends_at
                else None,
                "trial_days_left": trial_days_left,
                "current_period_start": subscription.current_period_start.isoformat()
                if subscription and subscription.current_period_start
                else None,
                "current_period_end": subscription.current_period_end.isoformat()
                if subscription and subscription.current_period_end
                else None,
                "seats": seats,
                "price_per_operator_uzs": price,
                "total_uzs": seats * price,
                "payments": payments,
            }
        )
