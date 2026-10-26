"""Remote Dial core: socket auth, online registry, dialing, ack/status.

Message names/fields follow the app's SocketContract.kt exactly
(BACKEND_REMOTE_DIAL_CONTRACT.md in the mobile repo).

Online registry: one cache key per (company, device) with a short TTL,
refreshed by the device's socket (its ping loop and every frame); the
socket deletes it on disconnect. Cache = Redis in every environment, so the
WebSocket service and the web workers see the same registry.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, timedelta
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Device, OperatorProfile, User
from apps.api.auth import require_active_company
from apps.api.errors import ApiError
from apps.core import domains
from apps.core.models import AuditLog
from apps.core.phone import NATIONAL_LENGTH, normalize_phone

from .models import DialCommand

ONLINE_TTL_SECONDS = 70  # > 2 × the 25 s ping interval
# The phone acks only AFTER the operator confirms (up to 30 s, app 1.16.1):
# a command stays "sent" (awaiting confirmation) until then.
ACK_TIMEOUT = timedelta(seconds=60)
# Same as the phone's own limit (1 per 10 s, 20/h) — never send a command
# it would refuse as rate_limited.
DEVICE_MIN_INTERVAL = timedelta(seconds=10)
DEVICE_PER_HOUR = 20
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
    # Operator confirmation on the phone (app 1.16+).
    "user_declined",
    "timeout",
    "expired",  # issued_at missing or > 60 s old on the phone (replay guard)
    "rate_limited",  # the phone's own limit
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


def group_name(company_id: int, operator_id: int, device_id: str) -> str:
    """Dial routing group — bound to the OPERATOR as well as the phone, so
    another operator claiming the same device_id can never receive it."""
    return f"dev_{company_id}_{operator_id}_{device_id}"


def operator_group(company_id: int, operator_id: int) -> str:
    return f"op_{company_id}_{operator_id}"


def company_group(company_id: int) -> str:
    return f"co_{company_id}"


def key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _online_key(company_id: int, device_id: str) -> str:
    return f"dial:online:{company_id}:{device_id}"


# ── Socket side ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DeviceSession:
    company_id: int
    operator_id: int
    device_id: str
    channel: str
    key_hash: str = ""  # sha256 of the api_key the socket logged in with


def authenticate_socket(
    api_key: Any, raw_device_id: Any, host: str
) -> tuple[int, int, str, str] | None:
    """Same checks as REST authenticate_device: active operator by api_key,
    device-host/tenant guard, active (not suspended / trial-expired)
    company — and the phone must not be claimed right now by ANOTHER
    operator's live socket. Returns (company_id, operator_id, device_id,
    key_hash) or None."""
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
    claim = online(operator.company_id, device_id)
    if claim and claim.get("operator_id") != operator.pk:
        return None  # someone else is logged in on this phone right now
    Device.all_objects.update_or_create(
        company=operator.company,
        operator=operator,
        device_id=device_id,
        defaults={"last_seen_at": timezone.now()},
    )
    return operator.company_id, operator.pk, device_id, key_hash(api_key)


def session_valid(session: DeviceSession) -> bool:
    """Still allowed? Operator active, same api_key, company usable."""
    operator = (
        OperatorProfile.all_objects.select_related("company")
        .filter(pk=session.operator_id, company_id=session.company_id, is_active=True)
        .first()
    )
    if operator is None or not hmac.compare_digest(key_hash(operator.api_key), session.key_hash):
        return False
    try:
        require_active_company(operator.company)
    except ApiError:
        return False
    return True


def revoke(group: str) -> None:
    """Close every socket in ``group`` now (consumer handler session_revoke)."""
    async_to_sync(get_channel_layer().group_send)(group, {"type": "session.revoke"})


def revoke_operator(company_id: int, operator_id: int) -> None:
    revoke(operator_group(company_id, operator_id))


def revoke_company(company_id: int) -> None:
    revoke(company_group(company_id))


def mark_online(session: DeviceSession, connected_at: str) -> None:
    cache.set(
        _online_key(session.company_id, session.device_id),
        {
            "company_id": session.company_id,
            "operator_id": session.operator_id,
            "device_id": session.device_id,
            "channel": session.channel,
            "key_hash": session.key_hash,
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
    # Only this company's commands addressed to THIS device AND operator.
    command: DialCommand | None = DialCommand.all_objects.filter(
        pk=command_id,
        company_id=session.company_id,
        device_id=session.device_id,
        operator_id=session.operator_id,
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


INVALID_NUMBER_MESSAGE = "Raqam noto'g'ri: faqat raqamlar (7–15 ta), boshida + bo'lishi mumkin"
NOT_ALLOWED_MESSAGE = "Bu yo'nalishga masofaviy qo'ng'iroq ruxsat etilmagan"
DEFAULT_ALLOWED_CODES = "998,992,996,7,993"
_SEPARATORS = re.compile(r"[\s\-()]")
_DIGITS_ONLY = re.compile(r"\+?[0-9]{7,15}")


def allowed_codes(phone_code: str) -> set[str]:
    """Country codes a remote dial may go to: the company's own code plus
    DIAL_ALLOWED_CODES (setting or env, default 998,992,996,7,993; empty →
    the company's code only). Blocks premium/international destinations."""
    raw = getattr(settings, "DIAL_ALLOWED_CODES", None)
    if raw is None:
        raw = os.environ.get("DIAL_ALLOWED_CODES", DEFAULT_ALLOWED_CODES)
    codes = {c.strip().lstrip("+") for c in str(raw).split(",")}
    return {c for c in codes if c.isdigit()} | ({phone_code} if phone_code else set())


def normalize_number(raw: Any, phone_code: str) -> str:
    """Strict: digits (7–15) with an optional leading + after stripping
    spaces/dashes/parens — so no USSD/MMI (*, #), pauses (, ; p w) or
    letters; normalized with the company code; country code allow-listed."""
    text = _SEPARATORS.sub("", str(raw or ""))
    if not _DIGITS_ONLY.fullmatch(text):
        raise DialError("invalid_number", INVALID_NUMBER_MESSAGE, 400)
    number = normalize_phone(text, phone_code)
    if not _E164.fullmatch(number):
        raise DialError("invalid_number", INVALID_NUMBER_MESSAGE, 400)
    matches = [code for code in allowed_codes(phone_code) if number.startswith(f"+{code}")]
    if not matches:
        raise DialError("destination_not_allowed", NOT_ALLOWED_MESSAGE, 400)
    # The country's exact national length when known (+998 → 9 digits, …).
    code = max(matches, key=len)
    national = NATIONAL_LENGTH.get(code)
    if national is not None and len(number) - 1 - len(code) != national:
        raise DialError("invalid_number", INVALID_NUMBER_MESSAGE, 400)
    return number


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def display_name(user: User) -> str:
    """Plain-text requester name for the phone's confirmation (≤ 64)."""
    name = user.get_full_name() or user.email or user.username or ""
    return " ".join(_CONTROL.sub(" ", name).split())[:64]


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


def _marker_still_valid(company_id: int, marker: dict[str, Any], devices: Any) -> bool:
    """Re-validate the target before sending (not just the online marker)."""
    try:
        operator_id = int(marker.get("operator_id"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if not devices.filter(operator_id=operator_id).exists():
        return False
    return session_valid(
        DeviceSession(
            company_id,
            operator_id,
            str(marker.get("device_id")),
            "",
            str(marker.get("key_hash") or ""),
        )
    )


def _dial(company: Any, user: User, device_id: str, raw_number: Any, key: str) -> DialCommand:
    devices = Device.all_objects.filter(company=company, device_id=device_id).select_related(
        "operator"
    )
    if not device_id or not devices.exists():
        raise DialError("device_not_found", "device not found", 404)
    try:
        require_active_company(company)
    except ApiError:
        raise DialError("subscription_inactive", "company subscription is inactive", 402) from None
    marker = online(company.pk, device_id)
    if marker and not _marker_still_valid(company.pk, marker, devices):
        # Stale/revoked session (key rotated, operator off): never send to it.
        revoke_operator(company.pk, int(marker["operator_id"]))
        marker = None
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
            group_name(company.pk, operator_id, device_id),
            {
                "type": "dial.command",
                "payload": {
                    "type": "call.dial",
                    "command_id": str(command.pk),
                    "number": number,
                    # Mandatory for the phone (≤ 60 s old): server clock, UTC.
                    "issued_at": timezone.now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    # Who asked — the phone shows it in the confirmation prompt.
                    "requested_by": display_name(user),
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


# ── Failed socket logins per client IP (connection-flood / guessing) ──────
AUTH_FAIL_LIMIT = 20
AUTH_FAIL_WINDOW_SECONDS = 600


def client_ip(scope: dict[str, Any]) -> str:
    """nginx sets X-Real-IP to $remote_addr (overwrites any client value);
    without a proxy, the socket peer."""
    headers = dict(scope.get("headers") or [])
    real: str = headers.get(b"x-real-ip", b"").decode(errors="replace").strip()
    if real:
        return real[:64]
    client = scope.get("client") or ("", 0)
    peer: str = str(client[0])[:64]
    return peer


def _fail_key(ip: str) -> str:
    return f"dial:wsfail:{ip}"


def auth_blocked(ip: str) -> bool:
    return bool(ip) and int(cache.get(_fail_key(ip)) or 0) >= AUTH_FAIL_LIMIT


def note_auth_failure(ip: str) -> None:
    if not ip:
        return
    key = _fail_key(ip)
    if not cache.add(key, 1, AUTH_FAIL_WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, AUTH_FAIL_WINDOW_SECONDS)
