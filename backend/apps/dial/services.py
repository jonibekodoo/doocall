"""Remote Dial core: socket auth, online registry, dialing, ack/status.

Message names/fields follow the app's SocketContract.kt exactly
(BACKEND_REMOTE_DIAL_CONTRACT.md in the mobile repo).

Online registry: one cache key per (company, device) with a short TTL,
refreshed by the device's socket (its ping loop and every frame); the
socket deletes it on disconnect. Cache = Redis in every environment, so the
WebSocket service and the web workers see the same registry.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, timedelta
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Device, OperatorProfile, User
from apps.api.auth import require_active_company
from apps.api.errors import ApiError
from apps.core import domains
from apps.core.models import AuditLog
from apps.core.phone import normalize_phone

from .models import DialCommand

ONLINE_TTL_SECONDS = 70  # > 2 × the 25 s ping interval
ACK_TIMEOUT = timedelta(seconds=30)
DEVICE_MIN_INTERVAL = timedelta(seconds=5)
DEVICE_PER_HOUR = 30
USER_MIN_INTERVAL = timedelta(seconds=2)
USER_PER_HOUR = 120
IDEMPOTENCY_WINDOW = timedelta(seconds=60)

REJECT_REASONS = {
    "permission_denied",
    "invalid_number",
    "another_call_active",
    "sim_disabled",
    "duplicate",
    "feature_disabled",
}
SIM_MODES = {"auto", "device_picker"}
CAUSES = {"answered", "no_answer", "rejected", "busy", "failed"}
STATE_TO_STATUS = {
    "dialing": DialCommand.Status.DIALING,
    "active": DialCommand.Status.ACTIVE,
    "disconnected": DialCommand.Status.DISCONNECTED,
    "failed": DialCommand.Status.FAILED,
}
# Progress order: an update never moves a command backwards; terminal
# states are final. "expired" can still be overtaken by a late real ack
# (the phone did get the command), "offline" was never sent at all.
RANK: dict[str, int] = {
    DialCommand.Status.SENT: 0,
    DialCommand.Status.EXPIRED: 0,
    DialCommand.Status.RECEIVED: 1,
    DialCommand.Status.DIALING: 2,
    DialCommand.Status.ACTIVE: 3,
}
TERMINAL: set[str] = {
    DialCommand.Status.REJECTED,
    DialCommand.Status.DISCONNECTED,
    DialCommand.Status.FAILED,
    DialCommand.Status.OFFLINE,
}

_DEVICE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")
_E164 = re.compile(r"\+[1-9][0-9]{6,14}")


def clean_device_id(raw: Any) -> str:
    """Group/key-safe device id (ANDROID_ID is 16 hex chars)."""
    return _DEVICE_ID_RE.sub("", str(raw or ""))[:64]


def group_name(company_id: int, device_id: str) -> str:
    return f"dev_{company_id}_{device_id}"


def _online_key(company_id: int, device_id: str) -> str:
    return f"dial:online:{company_id}:{device_id}"


# ── Socket side ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DeviceSession:
    company_id: int
    operator_id: int
    device_id: str
    channel: str


def authenticate_socket(api_key: Any, raw_device_id: Any, host: str) -> tuple[int, int, str] | None:
    """Same checks as REST authenticate_device: active operator by api_key,
    device-host/tenant guard, active (not suspended / trial-expired)
    company. Returns (company_id, operator_id, device_id) or None."""
    device_id = clean_device_id(raw_device_id)
    if not isinstance(api_key, str) or not api_key or not device_id:
        return None
    operator = (
        OperatorProfile.all_objects.select_related("company")
        .filter(api_key=api_key, is_active=True)
        .first()
    )
    if operator is None or domains.device_login_denied(host):
        return None
    sub = domains.company_subdomain(host)
    if sub is not None and operator.company.slug != sub:
        return None
    try:
        require_active_company(operator.company)
    except ApiError:
        return None
    Device.all_objects.update_or_create(
        company=operator.company,
        operator=operator,
        device_id=device_id,
        defaults={"last_seen_at": timezone.now()},
    )
    return operator.company_id, operator.pk, device_id


def mark_online(session: DeviceSession, connected_at: str) -> None:
    cache.set(
        _online_key(session.company_id, session.device_id),
        {
            "company_id": session.company_id,
            "operator_id": session.operator_id,
            "device_id": session.device_id,
            "channel": session.channel,
            "connected_at": connected_at,
            "last_seen": timezone.now().isoformat(),
        },
        ONLINE_TTL_SECONDS,
    )


def mark_offline(session: DeviceSession) -> None:
    """Drop the marker — unless a newer connection of the device owns it."""
    key = _online_key(session.company_id, session.device_id)
    current = cache.get(key)
    if current and current.get("channel") == session.channel:
        cache.delete(key)


def online(company_id: int, device_id: str) -> dict[str, Any] | None:
    marker = cache.get(_online_key(company_id, device_id))
    return marker if isinstance(marker, dict) else None


def _command_for(session: DeviceSession, raw_id: Any) -> DialCommand | None:
    try:
        command_id = uuid.UUID(str(raw_id))
    except (ValueError, TypeError):
        return None
    # Only this company's commands addressed to THIS device.
    command: DialCommand | None = DialCommand.all_objects.filter(
        pk=command_id, company_id=session.company_id, device_id=session.device_id
    ).first()
    return command


def _advance(command: DialCommand, status: str) -> bool:
    if command.status in TERMINAL:
        return False
    if status not in TERMINAL and RANK.get(status, 0) <= RANK.get(command.status, 0):
        return False
    command.status = status
    return True


def apply_ack(session: DeviceSession, frame: dict[str, Any]) -> bool:
    command = _command_for(session, frame.get("command_id"))
    if command is None:
        return False
    status = frame.get("status")
    fields = ["status", "updated_at"]
    if status == "received":
        if not _advance(command, DialCommand.Status.RECEIVED):
            return False
        mode = frame.get("sim_mode")
        command.sim_mode = mode if mode in SIM_MODES else ""
        slot = frame.get("used_sim_slot")
        command.used_sim_slot = slot if isinstance(slot, int) and slot in (0, 1) else None
        fields += ["sim_mode", "used_sim_slot"]
    elif status == "rejected":
        if not _advance(command, DialCommand.Status.REJECTED):
            return False
        reason = frame.get("reason")
        command.reject_reason = reason if reason in REJECT_REASONS else "unknown"
        fields.append("reject_reason")
    else:
        return False
    if command.acked_at is None:
        command.acked_at = timezone.now()
        fields.append("acked_at")
    command.save(update_fields=fields)
    return True


def apply_status(session: DeviceSession, frame: dict[str, Any]) -> bool:
    command = _command_for(session, frame.get("command_id"))
    status = STATE_TO_STATUS.get(frame.get("state"))  # type: ignore[arg-type]
    if command is None or status is None or not _advance(command, status):
        return False
    fields = ["status", "updated_at"]
    if status in (DialCommand.Status.DISCONNECTED, DialCommand.Status.FAILED):
        duration = frame.get("duration_sec")
        if isinstance(duration, int) and not isinstance(duration, bool) and 0 <= duration < 86400:
            command.duration_sec = duration
            fields.append("duration_sec")
        cause = frame.get("cause")
        command.cause = cause if cause in CAUSES else ""
        fields.append("cause")
    command.save(update_fields=fields)
    return True


# ── Cabinet side ──────────────────────────────────────────────────────────
class DialError(Exception):
    def __init__(self, code: str, message: str, status: int, **extra: Any) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


def operator_of(user: User) -> OperatorProfile | None:
    profile: OperatorProfile | None = OperatorProfile.all_objects.filter(user=user).first()
    return profile


def normalize_number(raw: Any, phone_code: str) -> str:
    text = str(raw or "").strip()
    number = normalize_phone(text, phone_code) if text else ""
    if "*" in text or "#" in text or not _E164.fullmatch(number):
        raise DialError("invalid_number", "number must be a full phone number (E.164)", 400)
    return number


def expire_stale(company_id: int) -> int:
    """Commands the phone never acknowledged within 30 s."""
    expired: int = DialCommand.all_objects.filter(
        company_id=company_id,
        status=DialCommand.Status.SENT,
        acked_at__isnull=True,
        created_at__lt=timezone.now() - ACK_TIMEOUT,
    ).update(status=DialCommand.Status.EXPIRED, updated_at=timezone.now())
    return expired


def _rate_limit(company_id: int, device_id: str, user: User) -> None:
    now = timezone.now()
    recent = DialCommand.all_objects.filter(company_id=company_id)
    by_device = recent.filter(device_id=device_id)
    by_user = recent.filter(created_by=user)
    if (
        by_device.filter(created_at__gte=now - DEVICE_MIN_INTERVAL).exists()
        or by_device.filter(created_at__gte=now - timedelta(hours=1)).count() >= DEVICE_PER_HOUR
        or by_user.filter(created_at__gte=now - USER_MIN_INTERVAL).exists()
        or by_user.filter(created_at__gte=now - timedelta(hours=1)).count() >= USER_PER_HOUR
    ):
        raise DialError("rate_limited", "too many dial requests — wait a moment", 429)


def dial(
    *, company: Any, user: User, raw_device_id: Any, raw_number: Any, idempotency_key: Any = ""
) -> DialCommand:
    """Create the command and push call.dial to the device if it is online.
    Offline → status "offline" and NOTHING is queued (no surprise calls)."""
    device_id = clean_device_id(raw_device_id)
    key = str(idempotency_key or "").strip()[:64]
    if key:
        previous: DialCommand | None = DialCommand.all_objects.filter(
            company=company,
            created_by=user,
            idempotency_key=key,
            created_at__gte=timezone.now() - IDEMPOTENCY_WINDOW,
        ).first()
        if previous is not None:
            return previous  # client retry: same command, never re-sent
        lock = f"dial:idem:{user.pk}:{key}"
        if not cache.add(lock, 1, int(IDEMPOTENCY_WINDOW.total_seconds())):
            raise DialError("duplicate_request", "the same request is already being processed", 409)
        try:
            return _dial(company, user, device_id, raw_number, key)
        except Exception:
            cache.delete(lock)  # a failed attempt must not block the corrected retry
            raise
    return _dial(company, user, device_id, raw_number, key)


def _dial(company: Any, user: User, device_id: str, raw_number: Any, key: str) -> DialCommand:
    devices = Device.all_objects.filter(company=company, device_id=device_id).select_related(
        "operator"
    )
    if not device_id or not devices.exists():
        raise DialError("device_not_found", "device not found", 404)
    marker = online(company.pk, device_id)
    # The operator the phone is logged in as right now (else the last known).
    if marker:
        operator_id = int(marker["operator_id"])
    else:
        last = devices.order_by("-last_seen_at", "-pk").first()
        operator_id = last.operator_id if last else 0
    if not user.is_company_admin:
        own = operator_of(user)
        if own is None or own.pk != operator_id or not devices.filter(operator=own).exists():
            raise DialError("forbidden", "you can only dial from your own device", 403)
    number = normalize_number(raw_number, company.phone_code)
    _rate_limit(company.pk, device_id, user)

    command: DialCommand = DialCommand.all_objects.create(
        company=company,
        created_by=user,
        operator_id=operator_id,
        device_id=device_id,
        number=number,
        idempotency_key=key,
        status=DialCommand.Status.SENT if marker else DialCommand.Status.OFFLINE,
    )
    AuditLog.objects.create(
        company=company,
        actor=user,
        action="dial.requested",
        target_model="dial.DialCommand",
        target_id=str(command.pk),
        changes={
            "device_id": device_id,
            "operator_id": operator_id,
            "number": number,
            "status": command.status,
        },
    )
    if marker:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            group_name(company.pk, device_id),
            {
                "type": "dial.command",
                "payload": {
                    "type": "call.dial",
                    "command_id": str(command.pk),
                    "number": number,
                    "issued_at": command.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
        )
    return command


def visible_commands(user: User) -> Any:
    qs = DialCommand.objects.select_related("operator")
    if user.is_company_admin:
        return qs
    own = operator_of(user)
    return qs.filter(Q(created_by=user) | Q(operator=own)) if own else qs.filter(created_by=user)
