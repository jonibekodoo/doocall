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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from apps.calls.models import CallRecord

TIMEOUT = 15

# Fields the cabinet must fill before an integration can be enabled.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("base_url", "access_token"),
    "bitrix24": ("webhook_url",),
    "odoo": ("url", "db", "login", "api_key"),
}

# Values masked in GET responses and preserved on save when left masked.
SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "amocrm": ("access_token",),
    "bitrix24": ("webhook_url",),
    "odoo": ("api_key",),
}


class ProviderError(Exception):
    """Delivery/validation failure surfaced to the cabinet UI and status row."""


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
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode(errors="replace")
        raise ProviderError(f"HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ProviderError(f"connection failed: {exc.reason}") from None
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        raise ProviderError("non-JSON response") from None


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


def _amo_call_payload(
    config: dict[str, Any], record: CallRecord, record_url: str | None
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
    if responsible := str(config.get("responsible_user_id") or "").strip():
        try:
            payload["responsible_user_id"] = int(responsible)
        except ValueError:
            pass  # misconfigured — the call still lands, just unassigned
    return payload


def _amo_call_landed(body: Any) -> bool:
    """True when amoCRM attached the call to some entity (contact/deal)."""
    calls = ((body or {}).get("_embedded") or {}).get("calls") or []
    return any(entry.get("entity_id") for entry in calls)


def _amocrm_create_contact(config: dict[str, Any], record: CallRecord) -> None:
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
    if responsible := str(config.get("responsible_user_id") or "").strip():
        try:
            contact["responsible_user_id"] = int(responsible)
        except ValueError:
            pass
    body = _http_json(f"{base}/api/v4/contacts", [contact], headers=_amo_headers(config))
    created = ((body or {}).get("_embedded") or {}).get("contacts") or []
    if not created:
        raise ProviderError(
            f"amoCRM: contact for {record.counterparty_number} could not be created"
        )


def _amocrm_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    base = _clean_base(config["base_url"])
    payload = [_amo_call_payload(config, record, record_url)]
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
    _amocrm_create_contact(config, record)
    body = _http_json(url, payload, headers=_amo_headers(config))
    if not _amo_call_landed(body):
        errors = (body or {}).get("errors") or body
        raise ProviderError(f"amoCRM rejected the call: {json.dumps(errors)[:300]}")


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
    if "error" in body:
        raise ProviderError(f"{method}: {body.get('error_description') or body['error']}")
    return body.get("result")


def _bitrix24_test(config: dict[str, Any]) -> str:
    result = _b24_call(config, "profile", {})
    return str(result.get("NAME") or result.get("ID") or "ok")


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


def _bitrix24_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    user_id = int(config.get("user_id") or 1)
    registered = _b24_call(
        config,
        "telephony.externalcall.register",
        {
            "USER_ID": user_id,
            "PHONE_NUMBER": record.counterparty_number,
            "TYPE": 2 if record.call_type == CallRecord.CallType.INBOUND else 1,
            "CALL_START_DATE": record.start_time.isoformat(),
            # Unknown numbers: Bitrix24 creates the lead/contact itself.
            "CRM_CREATE": 1,
            "SHOW": 0,
            # Dedup guard: repeated dispatch of the same DooCall record
            # within 30 minutes reuses the registered call.
            "EXTERNAL_CALL_ID": record.server_id.hex,
        },
    )
    if not (registered or {}).get("CALL_ID"):
        raise ProviderError("telephony.externalcall.register returned no CALL_ID")
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
    if body.get("error"):
        message = body["error"].get("data", {}).get("message") or body["error"].get("message")
        raise ProviderError(f"Odoo: {str(message)[:300]}")
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
    partner_ids = _odoo_execute(
        config,
        uid,
        "res.partner",
        "search",
        ["|", ("phone", "like", tail), ("mobile", "like", tail)],
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


# ── Dispatch table ─────────────────────────────────────────────────────────
_TESTS = {"amocrm": _amocrm_test, "bitrix24": _bitrix24_test, "odoo": _odoo_test}
_SENDERS = {"amocrm": _amocrm_send, "bitrix24": _bitrix24_send, "odoo": _odoo_send}


def validate_config(provider: str, config: dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS.get(provider, ()) if not str(config.get(f) or "").strip()]
    if missing:
        raise ProviderError(f"missing fields: {', '.join(missing)}")


def test_connection(provider: str, config: dict[str, Any]) -> str:
    validate_config(provider, config)
    return _TESTS[provider](config)


def send_call(provider: str, config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    validate_config(provider, config)
    _SENDERS[provider](config, record, record_url)
