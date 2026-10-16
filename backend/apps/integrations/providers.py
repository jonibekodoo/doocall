"""CRM connector adapters — pure functions over ``CrmIntegration.config``.

Every adapter exposes two operations used by the views/tasks:

* ``test_connection(provider, config)`` — cheap credentials check.
* ``send_call(provider, config, record, record_url)`` — push one finished
  call into the CRM (contact/lead timeline entry with the recording link).

All HTTP goes through stdlib ``urllib`` (same as the webhook task — the
backend deliberately has no ``requests`` dependency).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.calls.models import CallRecord
from apps.core import netguard

if TYPE_CHECKING:
    from apps.companies.models import Company

logger = logging.getLogger(__name__)

TIMEOUT = 15

# Fields the cabinet must fill before an integration can be enabled.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("base_url", "access_token"),
    "bitrix24": ("webhook_url",),
    "odoo": ("url", "db", "login", "api_key"),
    "kotib": ("api_key", "webhook_url", "webhook_secret"),
}

# Values masked in GET responses and preserved on save when left masked.
SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("access_token",),
    "bitrix24": ("webhook_url",),
    "odoo": ("api_key",),
    # webhook_url embeds Kotib's secret token; doocall_api_key is the
    # Kotib-only public-API key. None of these leave the server.
    "kotib": ("api_key", "webhook_url", "webhook_secret", "doocall_api_key"),
}


class ProviderError(Exception):
    """Delivery/validation failure surfaced to the cabinet UI and status row."""


class CallSkipped(Exception):
    """The integration's own options say this call must not be sent (not a
    failure): recorded as an ok delivery with a "skipped" note."""


class KotibGone(ProviderError):
    """Kotib answered 410 — the integration was switched off on their side;
    the dispatcher disables it instead of retrying forever."""


def _http_json(
    url: str,
    payload: Any = None,
    *,
    headers: dict[str, str] | None = None,
    method: str | None = None,
) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 - company-configured URL
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method or ("POST" if body is not None else "GET"),
    )
    # Company-configured URL → SSRF guard: https/public-only, IP-pinned, no
    # redirects (apps.core.netguard). Remote bodies are never echoed raw.
    try:
        with netguard.open_url(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except netguard.UnsafeURL as exc:
        raise ProviderError(
            f"CRM manzili xavfsizlik tekshiruvidan o'tmadi: {exc} — "
            "integratsiya sozlamalarida manzilni tuzating"
        ) from None
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise ProviderError(f"HTTP {exc.code}: redirect refused") from None
        summary = _error_summary(exc.read(MAX_ERROR_BYTES))
        message = f"HTTP {exc.code}: {summary}" if summary else f"HTTP {exc.code}"
        raise ProviderError(message) from None
    except (urllib.error.URLError, OSError):
        raise ProviderError("connection failed") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ProviderError("response too large")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        raise ProviderError("non-JSON response") from None


MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_ERROR_BYTES = 16 * 1024
# Fields of a JSON error body that may be shown to the cabinet (Bitrix24:
# error/error_description; amoCRM: title/detail, also inside "errors").
_ERROR_KEYS = ("error", "error_description", "title", "detail")


def safe_text(value: Any, limit: int = 200) -> str:
    """Plain text for the cabinet: tags removed, whitespace collapsed, cut."""
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    return " ".join(text.split())[:limit]


def _error_summary(raw: bytes) -> str:
    """Known error fields of a JSON error body; non-JSON bodies → ""."""
    try:
        body = json.loads(raw)
    except ValueError:
        return ""
    items = [body] if isinstance(body, dict) else []
    if isinstance(body, dict) and isinstance(body.get("errors"), list):
        items += [e for e in body["errors"] if isinstance(e, dict)]
    parts = [
        str(item[key])
        for item in items
        for key in _ERROR_KEYS
        if isinstance(item.get(key), str | int | float) and item.get(key) != ""
    ]
    # amoCRM: {"validation-errors": [{"errors": [{"path", "code", "detail"}]}]}
    if isinstance(body, dict) and isinstance(body.get("validation-errors"), list):
        for group in body["validation-errors"]:
            for err in (group.get("errors") if isinstance(group, dict) else None) or []:
                if isinstance(err, dict) and isinstance(err.get("path"), str):
                    parts.append(f"{err['path']}: {err.get('code') or err.get('detail') or ''}")
    return safe_text("; ".join(dict.fromkeys(parts)))


def _clean_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


# ── amoCRM / Kommo ─────────────────────────────────────────────────────────
# https://www.amocrm.ru/developers/content/crm_platform/calls-api
AMO_STATUS = {  # call_status → amoCRM "результат звонка" enum
    CallRecord.CallStatus.ANSWERED: 4,  # разговор состоялся
    CallRecord.CallStatus.NO_ANSWER: 6,  # не дозвонился
    CallRecord.CallStatus.BUSY: 7,  # номер занят
    CallRecord.CallStatus.FAILED: 6,
}


def _amo_headers(config: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {config['access_token']}"}


def _amocrm_test(config: dict[str, Any]) -> str:
    base = _clean_base(config["base_url"])
    body = _http_json(f"{base}/api/v4/account", headers=_amo_headers(config))
    return str(body.get("name") or body.get("id") or "ok")


def amo_fallback_user(config: dict[str, Any]) -> int | None:
    """Integration-wide responsible user (``responsible_user_id``) or None."""
    try:
        value = int(str(config.get("responsible_user_id") or "").strip())
    except ValueError:
        return None  # misconfigured — calls still land, just unassigned
    return value if value > 0 else None


def amo_user_for(config: dict[str, Any], operator_id: int | None) -> int | None:
    """amoCRM responsible user for a DooCall operator: ``user_map`` entry,
    else ``responsible_user_id``, else None (field omitted)."""
    mapped = (config.get("user_map") or {}).get(str(operator_id)) if operator_id else None
    try:
        return int(mapped) if mapped else amo_fallback_user(config)
    except (TypeError, ValueError):
        return amo_fallback_user(config)


def as_dict(value: Any) -> dict[str, Any]:
    """``value`` if it is a JSON object, else {} (defensive parsing)."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


AMO_USERS_PAGE = 250
AMO_USERS_CAP = 500
AMO_USERS_MAX_PAGES = 4


def amocrm_users(config: dict[str, Any]) -> list[dict[str, Any]]:
    """amoCRM users via GET /api/v4/users (page by page on OUR base URL —
    the ``_links.next`` href itself is never followed), active ones only."""
    base = _clean_base(config["base_url"])
    users: list[dict[str, Any]] = []
    for page in range(1, AMO_USERS_MAX_PAGES + 1):
        body = _http_json(
            f"{base}/api/v4/users?limit={AMO_USERS_PAGE}&page={page}&with=role",
            headers=_amo_headers(config),
        )
        if not isinstance(body, dict):
            raise ProviderError("amoCRM users: unexpected response")
        rows = as_list(as_dict(body.get("_embedded")).get("users"))
        page_users = [row for row in rows if isinstance(row, dict)]
        for row in page_users:
            if as_dict(row.get("rights")).get("is_active") is False:
                continue
            users.append(row)
        links = as_dict(body.get("_links"))
        if not page_users or "next" not in links or len(users) >= AMO_USERS_CAP:
            break
    return users[:AMO_USERS_CAP]


def _amo_call_payload(
    config: dict[str, Any], record: CallRecord, record_url: str | None, user_id: int | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "direction": "inbound"
        if record.call_type == CallRecord.CallType.INBOUND
        else "outbound",
        "uniq": record.server_id.hex,
        "duration": record.duration,
        "source": "DooCall",
        "link": record_url or "",
        "phone": record.counterparty_number,
        "call_result": record.resolved_name or record.counterparty_name or "",
        "call_status": AMO_STATUS.get(record.call_status, 6),
        "created_at": int(record.start_time.timestamp()),
    }
    if user_id:
        payload["responsible_user_id"] = user_id
    return payload


def _amo_call_landed(body: Any) -> bool:
    """True when amoCRM attached the call to some entity (contact/deal)."""
    calls = ((body or {}).get("_embedded") or {}).get("calls") or []
    return any(entry.get("entity_id") for entry in calls)


def _amocrm_create_contact(config: dict[str, Any], record: CallRecord, user_id: int | None) -> None:
    """amoCRM adds a call ONLY when the phone matches an existing entity —
    for unknown numbers we create the contact first, then retry the call."""
    base = _clean_base(config["base_url"])
    contact: dict[str, Any] = {
        "name": record.resolved_name
        or record.counterparty_name
        or record.counterparty_number,
        "custom_fields_values": [
            {
                "field_code": "PHONE",
                "values": [{"value": record.counterparty_number, "enum_code": "WORK"}],
            }
        ],
    }
    if user_id:
        contact["responsible_user_id"] = user_id
    body = _http_json(f"{base}/api/v4/contacts", [contact], headers=_amo_headers(config))
    created = ((body or {}).get("_embedded") or {}).get("contacts") or []
    if not created:
        raise ProviderError(
            f"amoCRM: contact for {record.counterparty_number} could not be created"
        )


def _amocrm_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    # Per-operator manager (user_map) with responsible_user_id as fallback.
    user_id = amo_user_for(config, record.operator_id)
    fallback = amo_fallback_user(config)
    try:
        _amocrm_send_as(config, record, record_url, user_id)
    except ProviderError as exc:
        if user_id == fallback or "responsible_user_id" not in str(exc):
            raise
        # Mapped user unknown/inactive in amoCRM → the fallback manager.
        logger.warning(
            "amocrm: mapped user %s rejected for call %s (%s); using fallback %s",
            user_id,
            record.pk,
            exc,
            fallback,
        )
        _amocrm_send_as(config, record, record_url, fallback)


def _amocrm_send_as(
    config: dict[str, Any], record: CallRecord, record_url: str | None, user_id: int | None
) -> None:
    base = _clean_base(config["base_url"])
    payload = [_amo_call_payload(config, record, record_url, user_id)]
    url = f"{base}/api/v4/calls"
    # "Entity not found" (status 263) arrives as HTTP 400 — treat it as
    # "phone unknown", not as a hard failure.
    try:
        if _amo_call_landed(_http_json(url, payload, headers=_amo_headers(config))):
            return
    except ProviderError as exc:
        if "Entity not found" not in str(exc):
            raise
    # Phone unknown to this amoCRM account → create the contact, retry once.
    _amocrm_create_contact(config, record, user_id)
    body = _http_json(url, payload, headers=_amo_headers(config))
    if not _amo_call_landed(body):
        errors = (body or {}).get("errors") or body
        raise ProviderError(f"amoCRM rejected the call: {safe_text(json.dumps(errors), 300)}")


# ── Bitrix24 (inbound webhook, telephony.externalcall.*) ───────────────────
# The webhook needs BOTH scopes: telephony (register/finish/attachRecord)
# and crm (timeline comment fallback for non-mp3/wav recordings).
B24_STATUS = {  # call_status → SIP code per apidocs.bitrix24.com (finish)
    CallRecord.CallStatus.ANSWERED: 200,  # successful call
    CallRecord.CallStatus.NO_ANSWER: 304,  # missed call
    CallRecord.CallStatus.BUSY: 486,  # busy
    CallRecord.CallStatus.FAILED: 603,  # declined
}

B24_AUDIO_EXTS = {"mp3", "wav"}  # attachRecord accepts only these


def _b24_call(config: dict[str, Any], method: str, params: dict[str, Any]) -> Any:
    base = _clean_base(config["webhook_url"])
    body = _http_json(f"{base}/{method}.json", params)
    if not isinstance(body, dict):
        raise ProviderError(f"{method}: unexpected response")
    if "error" in body:
        raise ProviderError(
            f"{method}: {safe_text(body.get('error_description') or body['error'])}"
        )
    return body.get("result")


def _bitrix24_test(config: dict[str, Any]) -> str:
    result = _b24_call(config, "profile", {})
    if not isinstance(result, dict):
        return "ok"
    return safe_text(result.get("NAME") or result.get("ID") or "ok")


def _b24_attach_recording(
    config: dict[str, Any],
    registered: dict[str, Any],
    record: CallRecord,
    record_url: str,
) -> None:
    """Attach the recording to the finished call; Bitrix24 only accepts
    mp3/wav files, so anything else lands as a CRM timeline comment with
    the permanent link instead."""
    audio = record.audios.first()
    ext = (audio.filename.rsplit(".", 1)[-1].lower() if audio and "." in audio.filename else "")
    if ext in B24_AUDIO_EXTS:
        try:
            _b24_call(
                config,
                "telephony.externalcall.attachrecord",
                {
                    "CALL_ID": registered["CALL_ID"],
                    "FILENAME": f"doocall-{record.server_id.hex}.{ext}",
                    "RECORD_URL": record_url,
                },
            )
            return
        except ProviderError:
            pass  # fall through to the timeline comment
    entity_id = registered.get("CRM_ENTITY_ID")
    if not entity_id:
        return  # nowhere to leave the link; the call itself is already logged
    _b24_call(
        config,
        "crm.timeline.comment.add",
        {
            "fields": {
                "ENTITY_ID": entity_id,
                "ENTITY_TYPE": str(registered.get("CRM_ENTITY_TYPE") or "lead").lower(),
                "COMMENT": f"DooCall — запись разговора: {record_url}",
            }
        },
    )


B24_USERS_CAP = 500  # user.get pages are 50 rows; stop after this many
B24_USERS_MAX_PAGES = 10


def b24_fallback_user(config: dict[str, Any]) -> int:
    try:
        return int(config.get("user_id") or 1)
    except (TypeError, ValueError):
        return 1


def b24_user_for(config: dict[str, Any], operator_id: int | None) -> int:
    """Bitrix24 USER_ID for a DooCall operator: ``user_map`` entry, else the
    integration-wide ``user_id`` (default 1)."""
    mapped = (config.get("user_map") or {}).get(str(operator_id)) if operator_id else None
    try:
        return int(mapped) if mapped else b24_fallback_user(config)
    except (TypeError, ValueError):
        return b24_fallback_user(config)


def bitrix24_users(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Active Bitrix24 users via ``user.get`` (needs the webhook's "user"
    scope). Follows ``next`` only while it moves forward and the page added
    rows — at most ``B24_USERS_MAX_PAGES`` requests, ``B24_USERS_CAP`` rows —
    so a misbehaving server can't keep a web worker busy."""
    base = _clean_base(config["webhook_url"])
    users: list[dict[str, Any]] = []
    start = 0
    for _ in range(B24_USERS_MAX_PAGES):
        body = _http_json(f"{base}/user.get.json", {"FILTER": {"ACTIVE": True}, "start": start})
        if not isinstance(body, dict):
            raise ProviderError("user.get: unexpected response")
        if "error" in body:
            detail = safe_text(body.get("error_description") or "")
            raise ProviderError(f"user.get: {safe_text(body.get('error'))}: {detail}")
        rows = body.get("result")
        page = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        users.extend(page)
        nxt = body.get("next")
        if not page or len(users) >= B24_USERS_CAP or isinstance(nxt, bool):
            break
        if not isinstance(nxt, int | str) or not str(nxt).isdigit() or int(nxt) <= start:
            break
        start = int(nxt)
    return users[:B24_USERS_CAP]


# Moizvonki-style card options (all non-secret, validated on save).
B24_CARD_MODES = ("auto", "lead", "contact", "deal", "none")
B24_DEFAULTS: dict[str, Any] = {
    "save_external_calls": True,  # False → only calls of numbers already in the CRM
    # unknown number → auto (lead on classic portals, contact + deal on
    # simple-CRM portals) | lead | contact | deal | none
    "create_card": "auto",
    "lead_source": "CALL",  # CRM_SOURCE / SOURCE_ID (crm.status SOURCE id)
    "only_answered": False,  # True → missed calls are not sent
}


def b24_options(config: dict[str, Any]) -> dict[str, Any]:
    """Card options with defaults (rows saved before the options existed)."""
    options = {**B24_DEFAULTS, **{k: config[k] for k in B24_DEFAULTS if k in config}}
    if options["create_card"] not in B24_CARD_MODES:
        options["create_card"] = B24_DEFAULTS["create_card"]
    return options


# crm.settings.mode.get (crm scope): 1 = classic (with leads), 2 = simple
# ("without leads": inquiries become deals + contacts/companies).
B24_CRM_MODES = {1: "classic", 2: "simple"}
B24_MODE_TTL = timedelta(hours=24)
# The only config keys a delivery may write back (tasks.deliver).
B24_MODE_CACHE_KEYS = ("crm_mode", "crm_mode_checked_at", "crm_mode_assumed")
B24_MODE_RETRY_TTL = timedelta(hours=1)  # after a failed detection
B24_LEAD_FALLBACK_NOTE = (
    "Bitrix24 portal lidlarsiz (oddiy CRM) — lid o'rniga kontakt yaratildi; "
    "sozlamada «avto», «kontakt» yoki «bitim»ni tanlang"
)


def b24_detect_mode(config: dict[str, Any]) -> tuple[str, bool]:
    """(``"classic"``/``"simple"``, assumed). A failure (e.g. no crm scope)
    assumes simple — never creating leads is the safe side."""
    try:
        value = _int_or_none(_b24_call(config, "crm.settings.mode.get", {}))
        mode = B24_CRM_MODES.get(value) if value is not None else None
    except ProviderError as exc:
        logger.warning("bitrix24 crm.settings.mode.get failed (%s); assuming simple CRM", exc)
        return "simple", True
    if mode is None:
        logger.warning("bitrix24 crm.settings.mode.get: unknown value; assuming simple CRM")
        return "simple", True
    return mode, False


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def b24_refresh_mode(config: dict[str, Any], *, force: bool = False) -> str:
    """Portal CRM mode, cached in ``config`` (crm_mode, crm_mode_checked_at,
    crm_mode_assumed) — re-detected after 24 h (1 h if it was assumed), or
    when ``force``. Mutates ``config``; the caller persists it."""
    checked = parse_datetime(str(config.get("crm_mode_checked_at") or ""))
    ttl = B24_MODE_RETRY_TTL if config.get("crm_mode_assumed") else B24_MODE_TTL
    cached = config.get("crm_mode")
    if not force and cached in ("classic", "simple") and checked and timezone.now() - checked < ttl:
        return str(cached)
    mode, assumed = b24_detect_mode(config)
    config.update(
        crm_mode=mode,
        crm_mode_checked_at=timezone.now().isoformat(),
        crm_mode_assumed=assumed,
    )
    return mode


def _b24_find_entities(config: dict[str, Any], phone: str) -> list[dict[str, Any]]:
    """CRM entities that already own ``phone`` (telephony scope)."""
    found = _b24_call(config, "telephony.externalcall.searchCrmEntities", {"PHONE_NUMBER": phone})
    return [e for e in found if isinstance(e, dict)] if isinstance(found, list) else []


def _b24_new_id(result: Any, method: str) -> int:
    try:
        return int(result)
    except (TypeError, ValueError):
        raise ProviderError(f"{method}: no id returned") from None


def _b24_create_contact(
    config: dict[str, Any], record: CallRecord, user_id: int, source: str
) -> int:
    name = record.resolved_name or record.counterparty_name or record.counterparty_number
    return _b24_new_id(
        _b24_call(
            config,
            "crm.contact.add",
            {
                "fields": {
                    "NAME": name,
                    "PHONE": [{"VALUE": record.counterparty_number, "VALUE_TYPE": "WORK"}],
                    "ASSIGNED_BY_ID": user_id,
                    "SOURCE_ID": source,
                    "OPENED": "Y",
                }
            },
        ),
        "crm.contact.add",
    )


def _b24_create_deal(
    config: dict[str, Any], record: CallRecord, contact_id: int, user_id: int, source: str
) -> int:
    return _b24_new_id(
        _b24_call(
            config,
            "crm.deal.add",
            {
                "fields": {
                    "TITLE": f"DooCall: {record.counterparty_number}",
                    "CONTACT_ID": contact_id,
                    "ASSIGNED_BY_ID": user_id,
                    "SOURCE_ID": source,
                }
            },
        ),
        "crm.deal.add",
    )


def _b24_register(
    config: dict[str, Any], record: CallRecord, user_id: int, binding: dict[str, Any]
) -> dict[str, Any]:
    registered = _b24_call(
        config,
        "telephony.externalcall.register",
        {
            "USER_ID": user_id,
            "PHONE_NUMBER": record.counterparty_number,
            "TYPE": 2 if record.call_type == CallRecord.CallType.INBOUND else 1,
            "CALL_START_DATE": record.start_time.isoformat(),
            "SHOW": 0,
            # Dedup guard: repeated dispatch of the same DooCall record
            # within 30 minutes reuses the registered call.
            "EXTERNAL_CALL_ID": record.server_id.hex,
            # CRM binding / card creation (see _bitrix24_send).
            **binding,
        },
    )
    if not (registered or {}).get("CALL_ID"):
        raise ProviderError("telephony.externalcall.register returned no CALL_ID")
    result: dict[str, Any] = registered
    return result


def _bitrix24_send(
    config: dict[str, Any], record: CallRecord, record_url: str | None
) -> str | None:
    """Register + finish the call (+ recording) under the operator's Bitrix24
    user. Unknown numbers get a card per ``create_card``; numbers already in
    the CRM are bound to their entity and never duplicated (also on retry —
    the search runs right before anything is created)."""
    options = b24_options(config)
    if options["only_answered"] and record.call_status != CallRecord.CallStatus.ANSWERED:
        _b24_log_branch(record, "skipped_unanswered", config)
        raise CallSkipped("missed call (only_answered)")
    # Portal mode matters for auto/lead: detect it on EVERY delivery path
    # (cached 24 h) — also when the number is already in the CRM, so the
    # first delivery fills the cache instead of waiting for an unknown caller.
    mode = (
        b24_refresh_mode(config)
        if options["create_card"] in ("auto", "lead")
        else str(config.get("crm_mode") or "")
    )
    # Per-operator user (user_map) with the integration-wide user as fallback.
    user_id = b24_user_for(config, record.operator_id)
    fallback = b24_fallback_user(config)
    source = options["lead_source"]
    note: str | None = None

    entities = _b24_find_entities(config, record.counterparty_number)
    binding: dict[str, Any]
    if entities:
        branch = "existing_entity"
        known = entities[0]
        binding = {"CRM_CREATE": 0}
        if known.get("CRM_ENTITY_TYPE") and known.get("CRM_ENTITY_ID"):
            binding |= {
                "CRM_ENTITY_TYPE": known["CRM_ENTITY_TYPE"],
                "CRM_ENTITY_ID": known["CRM_ENTITY_ID"],
            }
    elif not options["save_external_calls"]:
        _b24_log_branch(record, "skipped_unknown", config)
        raise CallSkipped("number not in Bitrix24 CRM (save_external_calls off)")
    else:
        card = options["create_card"]
        if card in ("auto", "lead") and mode == "simple":
            # Portals without leads never get one from us.
            if card == "lead":
                note = B24_LEAD_FALLBACK_NOTE
            card = "contact" if card == "lead" else "deal"
        elif card == "auto":
            card = "lead"
        binding = _b24_new_card(config, record, card, user_id, source)
        branch = B24_CARD_BRANCHES[card]

    try:
        registered = _b24_register(config, record, user_id, binding)
    except ProviderError as exc:
        if user_id == fallback:
            raise
        # Mapped user unknown/inactive in Bitrix24 → land on the fallback user.
        logger.warning(
            "bitrix24: mapped user %s rejected for call %s (%s); using fallback %s",
            user_id,
            record.pk,
            exc,
            fallback,
        )
        user_id = fallback
        registered = _b24_register(config, record, user_id, binding)
    _b24_call(
        config,
        "telephony.externalcall.finish",
        {
            "CALL_ID": registered["CALL_ID"],
            "USER_ID": user_id,
            "DURATION": record.duration,
            "STATUS_CODE": B24_STATUS.get(record.call_status, 603),
        },
    )
    if record_url:
        _b24_attach_recording(config, registered, record, record_url)
    _b24_log_branch(record, branch, config)
    return note


# Card actually made for an unknown number (after auto/lead resolution).
B24_CARD_BRANCHES = {
    "lead": "created_lead",
    "contact": "created_contact",
    "deal": "created_contact_deal",
    "none": "no_card",
}


def _b24_log_branch(record: CallRecord, branch: str, config: dict[str, Any]) -> None:
    """One structured line per Bitrix24 delivery (no numbers, no URLs)."""
    logger.info(
        "bitrix24 delivery company=%s call=%s branch=%s crm_mode=%s",
        record.company_id,
        record.pk,
        branch,
        config.get("crm_mode") or "unknown",
    )


def _b24_new_card(
    config: dict[str, Any], record: CallRecord, card: str, user_id: int, source: str
) -> dict[str, Any]:
    """Register binding for an unknown number (card ∈ lead/contact/deal/none)."""
    if card == "lead":
        # Bitrix24 creates the lead itself (classic portals only).
        return {"CRM_CREATE": 1, "CRM_SOURCE": source}
    if card == "none":
        return {"CRM_CREATE": 0}  # kept in telephony stats, no card
    contact_id = _b24_create_contact(config, record, user_id, source)
    if card == "deal":
        _b24_create_deal(config, record, contact_id, user_id, source)
    # The call activity binds to the contact; the deal links via it.
    return {"CRM_CREATE": 0, "CRM_ENTITY_TYPE": "CONTACT", "CRM_ENTITY_ID": contact_id}


# ── Odoo (JSON-RPC) ────────────────────────────────────────────────────────
def _odoo_rpc(config: dict[str, Any], service: str, method: str, args: list[Any]) -> Any:
    base = _clean_base(config["url"])
    body = _http_json(
        f"{base}/jsonrpc",
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        },
    )
    if not isinstance(body, dict):
        raise ProviderError("Odoo: unexpected response")
    if error := body.get("error"):
        error = error if isinstance(error, dict) else {"message": error}
        data = error.get("data") if isinstance(error.get("data"), dict) else {}
        raise ProviderError(f"Odoo: {safe_text(data.get('message') or error.get('message'))}")
    return body.get("result")


def _odoo_auth(config: dict[str, Any]) -> int:
    uid = _odoo_rpc(
        config, "common", "authenticate", [config["db"], config["login"], config["api_key"], {}]
    )
    if not uid:
        raise ProviderError("Odoo authentication failed (check db/login/api key)")
    return int(uid)


def _odoo_execute(
    config: dict[str, Any], uid: int, model: str, method: str, *args: Any, **kwargs: Any
) -> Any:
    return _odoo_rpc(
        config,
        "object",
        "execute_kw",
        [config["db"], uid, config["api_key"], model, method, list(args), kwargs],
    )


def _odoo_test(config: dict[str, Any]) -> str:
    return f"uid={_odoo_auth(config)}"


def _odoo_send_via_app(
    config: dict[str, Any], uid: int, record: CallRecord, record_url: str | None
) -> None:
    """Preferred path: the DooCall Odoo app (doocall.call) is installed —
    it links partner/lead, posts chatter and renders the audio player."""
    existing = _odoo_execute(
        config,
        uid,
        "doocall.call",
        "search_count",
        [[("server_id", "=", record.server_id.hex)]],
    )
    if existing:
        return
    _odoo_execute(
        config,
        uid,
        "doocall.call",
        "create",
        [
            {
                "call_id": record.call_id,
                "server_id": record.server_id.hex,
                "direction": "inbound"
                if record.call_type == CallRecord.CallType.INBOUND
                else "outbound",
                "status": record.call_status,
                "phone": record.counterparty_number,
                "operator": record.operator.user_name if record.operator else False,
                "duration": record.duration,
                "start_time": record.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "record_url": record_url or False,
            }
        ],
    )


def _odoo_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    uid = _odoo_auth(config)
    try:
        _odoo_send_via_app(config, uid, record, record_url)
        return
    except ProviderError:
        pass  # app not installed → legacy chatter-only delivery below
    tail = record.counterparty_number[-9:]  # match regardless of +998 formatting
    # Odoo 18+ res.partner'da "mobile" maydoni yo'q — faqat "phone".
    partner_ids = _odoo_execute(
        config,
        uid,
        "res.partner",
        "search",
        [("phone", "like", tail)],
        limit=1,
    )
    direction = "Kiruvchi" if record.call_type == CallRecord.CallType.INBOUND else "Chiquvchi"
    minutes, seconds = divmod(record.duration, 60)
    lines = [
        f"<b>DooCall: {direction} qo'ng'iroq</b>",
        f"Raqam: {record.counterparty_number}",
        f"Holat: {record.call_status} · Davomiylik: {minutes:02d}:{seconds:02d}",
        f"Vaqt: {record.start_time_local or record.start_time.isoformat()}",
    ]
    if record.resolved_name or record.counterparty_name:
        lines.insert(2, f"Mijoz: {record.resolved_name or record.counterparty_name}")
    if record_url:
        lines.append(f'<a href="{record_url}">Audio yozuvni tinglash</a>')
    body_html = "<br/>".join(lines)

    if partner_ids:
        _odoo_execute(
            config,
            uid,
            "res.partner",
            "message_post",
            partner_ids,
            body=body_html,
        )
        return
    # No matching contact → create a CRM lead (falls back to a contact when
    # the crm module is not installed on the target database).
    lead = {
        "name": f"DooCall {direction.lower()} {record.counterparty_number}",
        "phone": record.counterparty_number,
        "description": body_html.replace("<br/>", "\n"),
    }
    try:
        _odoo_execute(config, uid, "crm.lead", "create", [lead])
    except ProviderError:
        partner_id = _odoo_execute(
            config,
            uid,
            "res.partner",
            "create",
            [
                {
                    "name": record.resolved_name
                    or record.counterparty_name
                    or record.counterparty_number,
                    "phone": record.counterparty_number,
                }
            ],
        )
        _odoo_execute(config, uid, "res.partner", "message_post", [partner_id], body=body_html)


# ── Kotib Analytics (AI call analytics) ────────────────────────────────────
# Connect/disconnect are explicit calls from the cabinet; calls then flow as
# the signed call.received webhook to the URL Kotib returned on connect, and
# Kotib pulls the details itself via our public API (calls.get/users.list).
KOTIB_ERROR_MESSAGES = {  # fallback when Kotib sends no human message
    "INVALID_API_KEY": "Kotib API kaliti noto'g'ri",
    "MISSING_FIELD": "Kotib: majburiy maydon yetishmaydi",
    "INVALID_ACCOUNT": "Kotib: akkaunt nomi noto'g'ri formatda",
    "DOOCALL_AUTH_FAILED": "Kotib DooCall API kalitini rad etdi",
    "DOOCALL_UNAVAILABLE": (
        "Kotib DooCall API'ga ulana olmadi — birozdan keyin qayta urinib ko'ring"
    ),
    "NOT_FOUND": "Kotib: bu akkaunt ulanmagan",
}
KOTIB_GONE_ERROR = "Kotib: integratsiya o'chirilgan (410)"
# Public-API actions the Kotib-only key may call (read-only, per Kotib's spec).
KOTIB_ALLOWED_ACTIONS = frozenset({"account.info", "users.list", "calls.get", "calls.list"})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: they would carry X-API-Key / the signed call
    to wherever Kotib (or a hijacked DNS entry) points. 3xx → HTTPError."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_KOTIB_OPENER = urllib.request.build_opener(_NoRedirect)


def _kotib_open(request: urllib.request.Request) -> Any:
    return _KOTIB_OPENER.open(request, timeout=TIMEOUT)


def kotib_webhook_url_ok(url: str) -> bool:
    """The webhook URL must live under KOTIB_BASE_URL (https, same host and
    port, below the base path) — Kotib's answer can't point us elsewhere."""
    base = urllib.parse.urlsplit(_clean_base(settings.KOTIB_BASE_URL))
    try:
        parsed = urllib.parse.urlsplit(url)
        port, base_port = parsed.port, base.port
    except ValueError:
        return False
    segments = parsed.path.split("/")
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and bool(parsed.hostname)
        and parsed.hostname == base.hostname
        and port == base_port
        and parsed.path.startswith(f"{base.path.rstrip('/')}/")
        and ".." not in segments
        and "." not in segments
    )


class KotibError(ProviderError):
    """Connect/disconnect rejected by Kotib; ``code`` is Kotib's error_code."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _kotib_error(status: int, raw: bytes) -> KotibError:
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = str(body.get("error_code") or "")
    message = str(body.get("message") or "").strip() or KOTIB_ERROR_MESSAGES.get(
        code, f"Kotib: HTTP {status}"
    )
    return KotibError(message[:300], code=code, status=status)


def _kotib_post(path: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to Kotib's integration API. The key travels only in X-API-Key —
    it never appears in URLs, error messages or logs."""
    base = _clean_base(settings.KOTIB_BASE_URL)
    request = urllib.request.Request(  # noqa: S310 - fixed partner base URL
        f"{base}/{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with _kotib_open(request) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise _kotib_error(exc.code, exc.read()) from None
    except urllib.error.URLError as exc:
        raise KotibError(f"Kotib'ga ulanib bo'lmadi: {exc.reason}") from None
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        raise KotibError("Kotib: non-JSON response") from None
    if not isinstance(body, dict) or body.get("success") is False:
        raise _kotib_error(200, raw)
    return body


def kotib_connect(
    config_api_key: str,
    account: str,
    user_name: str,
    doocall_api_key: str,
    webhook_secret: str,
) -> dict[str, Any]:
    """Register (or refresh — idempotent) this account on Kotib's side.

    Returns ``{company, webhook_url, employees}``; ``employees`` may be
    ``None`` (Kotib could not list operators yet — the connection still
    stands)."""
    body = _kotib_post(
        "connect",
        config_api_key,
        {
            "account": account,
            "user_name": user_name,
            "api_key": doocall_api_key,
            "webhook_secret": webhook_secret,
        },
    )
    webhook_url = str(body.get("webhook_url") or "").strip()
    if not webhook_url:
        raise KotibError("Kotib: webhook_url javobda yo'q")
    if not kotib_webhook_url_ok(webhook_url):
        raise KotibError("Kotib: webhook_url noto'g'ri manzil")
    employees = body.get("employees")
    return {
        "company": str(body.get("company") or ""),
        "webhook_url": webhook_url,
        "employees": employees if isinstance(employees, dict) else None,
    }


def kotib_disconnect(api_key: str, account: str) -> None:
    """Tell Kotib to stop; 404 NOT_FOUND means it is already disconnected."""
    try:
        _kotib_post("disconnect", api_key, {"account": account})
    except KotibError as exc:
        if exc.status == 404:
            return
        raise


def _kotib_test(config: dict[str, Any], company: Company | None) -> str:
    """Re-run connect with the stored keys + secret (idempotent per Kotib's
    spec). Kotib gets only its own revocable key, never Company.api_key."""
    if company is None:
        raise ProviderError("Kotib: kompaniya topilmadi")
    if not config.get("doocall_api_key"):
        raise ProviderError("Kotib: integratsiyani qayta saqlang")
    result = kotib_connect(
        config["api_key"],
        company.slug,
        str(config.get("user_name") or ""),
        config["doocall_api_key"],
        config["webhook_secret"],
    )
    return result["company"] or "ok"


def _kotib_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    from apps.web.tasks import sign_webhook, webhook_payload

    if not kotib_webhook_url_ok(config["webhook_url"]):
        raise ProviderError("Kotib: webhook_url noto'g'ri manzil — re-save the integration")
    # Sign exactly the bytes that go on the wire.
    body = json.dumps(webhook_payload(record)).encode()
    request = urllib.request.Request(  # noqa: S310 - URL returned by Kotib connect
        config["webhook_url"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Doocall-Signature": sign_webhook(config["webhook_secret"], body),
        },
        method="POST",
    )
    # Errors name only the status: the webhook URL carries a secret token.
    try:
        with _kotib_open(request) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise ProviderError(f"Kotib: redirect refused (HTTP {exc.code})") from None
        if exc.code == 410:
            raise KotibGone(KOTIB_GONE_ERROR) from None
        if exc.code == 401:
            raise ProviderError("Kotib: signature rejected — re-save the integration") from None
        if exc.code == 404:
            raise ProviderError("Kotib: unknown webhook URL — re-save the integration") from None
        raise ProviderError(f"Kotib: HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ProviderError(f"Kotib: connection failed: {exc.reason}") from None


def kotib_wants(record: CallRecord) -> bool:
    """Kotib analyses only answered calls with speech; others are skipped."""
    return record.call_status == CallRecord.CallStatus.ANSWERED and record.duration > 0


# ── Dispatch table ─────────────────────────────────────────────────────────
_TESTS = {"amocrm": _amocrm_test, "bitrix24": _bitrix24_test, "odoo": _odoo_test}
_SENDERS: dict[str, Callable[[dict[str, Any], CallRecord, str | None], str | None]] = {
    "amocrm": _amocrm_send,
    "bitrix24": _bitrix24_send,
    "odoo": _odoo_send,
    "kotib": _kotib_send,
}


def validate_config(provider: str, config: dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS.get(provider, ()) if not str(config.get(f) or "").strip()]
    if missing:
        raise ProviderError(f"missing fields: {', '.join(missing)}")


def test_connection(
    provider: str, config: dict[str, Any], *, company: Company | None = None
) -> str:
    validate_config(provider, config)
    if provider == "kotib":
        return _kotib_test(config, company)
    return _TESTS[provider](config)


def send_call(
    provider: str, config: dict[str, Any], record: CallRecord, record_url: str | None
) -> str | None:
    """Deliver one call. Returns an optional warning note for the delivery
    row (e.g. a Bitrix24 lead turned into a contact on a simple-CRM portal).
    A sender may update cache keys in ``config`` (callers persist it)."""
    validate_config(provider, config)
    note: str | None = _SENDERS[provider](config, record, record_url)
    return note
