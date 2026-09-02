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


def _amocrm_test(config: dict[str, Any]) -> str:
    base = _clean_base(config["base_url"])
    body = _http_json(
        f"{base}/api/v4/account",
        headers={"Authorization": f"Bearer {config['access_token']}"},
    )
    return str(body.get("name") or body.get("id") or "ok")


def _amocrm_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    base = _clean_base(config["base_url"])
    payload = [
        {
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
    ]
    body = _http_json(
        f"{base}/api/v4/calls",
        payload,
        headers={"Authorization": f"Bearer {config['access_token']}"},
    )
    errors = (body or {}).get("errors")
    if errors:
        raise ProviderError(f"amoCRM rejected the call: {json.dumps(errors)[:300]}")


# ── Bitrix24 (inbound webhook, telephony.externalcall.*) ───────────────────
B24_STATUS = {  # call_status → SIP-style code Bitrix24 expects
    CallRecord.CallStatus.ANSWERED: 200,
    CallRecord.CallStatus.NO_ANSWER: 480,
    CallRecord.CallStatus.BUSY: 486,
    CallRecord.CallStatus.FAILED: 603,
}


def _b24_call(config: dict[str, Any], method: str, params: dict[str, Any]) -> Any:
    base = _clean_base(config["webhook_url"])
    body = _http_json(f"{base}/{method}.json", params)
    if "error" in body:
        raise ProviderError(f"{method}: {body.get('error_description') or body['error']}")
    return body.get("result")


def _bitrix24_test(config: dict[str, Any]) -> str:
    result = _b24_call(config, "profile", {})
    return str(result.get("NAME") or result.get("ID") or "ok")


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
            "CRM_CREATE": 1,
            "SHOW": 0,
        },
    )
    call_id = (registered or {}).get("CALL_ID")
    if not call_id:
        raise ProviderError("telephony.externalcall.register returned no CALL_ID")
    _b24_call(
        config,
        "telephony.externalcall.finish",
        {
            "CALL_ID": call_id,
            "USER_ID": user_id,
            "DURATION": record.duration,
            "STATUS_CODE": B24_STATUS.get(record.call_status, 603),
        },
    )
    if record_url:
        _b24_call(
            config,
            "telephony.externalcall.attachrecord",
            {
                "CALL_ID": call_id,
                "FILENAME": f"doocall-{record.server_id.hex}.mp3",
                "RECORD_URL": record_url,
            },
        )


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


def _odoo_send(config: dict[str, Any], record: CallRecord, record_url: str | None) -> None:
    uid = _odoo_auth(config)
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
