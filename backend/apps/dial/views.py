"""Cabinet Remote Dial API — /api/web/v1/dial*."""

from __future__ import annotations

from typing import Any, cast

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import Device, User
from apps.api.errors import ApiError, ErrorCode
from apps.web.permissions import CabinetView

from . import services
from .models import DialCommand


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def command_body(command: DialCommand) -> dict[str, Any]:
    operator = command.operator
    return {
        "command_id": str(command.pk),
        "device_id": command.device_id,
        "operator": {"id": operator.pk, "full_name": operator.full_name or operator.user_name}
        if operator
        else None,
        "number": command.number,
        "status": command.status,
        "reject_reason": command.reject_reason or None,
        "sim_mode": command.sim_mode or None,
        "used_sim_slot": command.used_sim_slot,
        "duration_sec": command.duration_sec,
        "cause": command.cause or None,
        "created_at": _iso(command.created_at),
        "acked_at": _iso(command.acked_at),
        "updated_at": _iso(command.updated_at),
    }


class DialDevicesView(CabinetView):
    @extend_schema(summary="Devices that can take a remote dial (online state)")
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        devices = Device.objects.select_related("operator").order_by("operator__full_name", "pk")
        if not user.is_company_admin:
            own = services.operator_of(user)
            devices = devices.filter(operator=own) if own else devices.none()
        rows = []
        for device in devices:
            marker = services.online(self.company.pk, services.clean_device_id(device.device_id))
            # Online only while the phone is logged in as THIS operator.
            is_online = bool(marker and marker.get("operator_id") == device.operator_id)
            rows.append(
                {
                    "device_id": device.device_id,
                    "operator": {
                        "id": device.operator_id,
                        "full_name": device.operator.full_name or device.operator.user_name,
                    },
                    "model": " ".join(p for p in (device.manufacturer, device.model) if p),
                    "online": is_online,
                    "last_seen": marker["last_seen"]
                    if is_online and marker
                    else _iso(device.last_seen_at),
                }
            )
        return Response({"success": True, "devices": rows})


class DialView(CabinetView):
    @extend_schema(summary="Ask a device to call a number (never queued when offline)")
    def post(self, request: Request) -> Response:
        services.expire_stale(self.company.pk)
        try:
            command = services.dial(
                company=self.company,
                user=cast(User, request.user),
                raw_device_id=request.data.get("device_id"),
                raw_number=request.data.get("number"),
                idempotency_key=request.data.get("idempotency_key"),
            )
        except services.DialError as exc:
            return Response(
                {"success": False, "error_code": exc.code, "message": exc.message, **exc.extra},
                status=exc.status,
            )
        if command.status == DialCommand.Status.OFFLINE:
            return Response(
                {
                    "success": False,
                    "error_code": "device_offline",
                    "command_id": str(command.pk),
                    "status": "offline",
                },
                status=409,
            )
        return Response({"success": True, "command_id": str(command.pk), "status": command.status})


class DialDetailView(CabinetView):
    @extend_schema(summary="Current state of one dial command (for UI polling)")
    def get(self, request: Request, command_id: Any) -> Response:
        services.expire_stale(self.company.pk)
        command = services.visible_commands(cast(User, request.user)).filter(pk=command_id).first()
        if command is None:
            raise ApiError(ErrorCode.MISSING_FIELD, "command not found", 404)
        return Response(
            {"success": True, "command": command_body(command), "now": _iso(timezone.now())}
        )
