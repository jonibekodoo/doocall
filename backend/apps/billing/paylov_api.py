"""Paylov Merchant API client — OAuth2 Bearer, direct card+OTP payments.

Sandbox base: https://dev.gw.paylov.uz/merchant/  (prod: https://gw2.paylov.uz/merchant/)
Flow for a one-time top-up:
  1. ``payment_without_registration(card, expire, amount_tiyin, account)`` → transactionId, OTP sent to cardholder.
  2. ``confirm_payment(transaction_id, otp)`` → payment completed.
Every call is logged to :class:`PaylovLog` (outbound). Card PAN/expiry are masked before logging.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.core.cache import cache

from .models import log_paylov

_TOKEN_CACHE_KEY = "paylov_access_token"
_TIMEOUT = 30


class PaylovError(Exception):
    def __init__(self, code: str, message: str = "", data: Any = None, http_status: int | None = None):
        self.code = code
        self.message = message or code
        self.data = data
        self.http_status = http_status
        super().__init__(f"{code}: {self.message}")


def _base() -> str:
    return (settings.PAYLOV_API_BASE or "").rstrip("/")


def _mask_card(body: dict[str, Any]) -> dict[str, Any]:
    """Never log a full PAN/expiry — keep only the last 4 digits."""
    b = dict(body)
    pan = str(b.get("cardNumber") or "")
    if pan:
        b["cardNumber"] = ("*" * max(len(pan) - 4, 0)) + pan[-4:] if len(pan) > 4 else "****"
    if b.get("expireDate"):
        b["expireDate"] = "****"
    return b


def _raw_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    return _raw_request("POST", url, body, headers)


def _raw_request(
    method: str, url: str, body: dict[str, Any] | None, headers: dict[str, str]
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed Paylov gateway host
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:  # Paylov returns JSON errors with 4xx
        raw = exc.read() or b""
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"error": {"code": "http_error", "message": raw[:200].decode(errors="replace")}}
    except urllib.error.URLError as exc:
        return 0, {"error": {"code": "connection_failed", "message": str(exc.reason)}}
    except (TimeoutError, OSError, ValueError) as exc:
        # Read timeout / dropped connection / non-JSON body: the outcome of the
        # call is UNKNOWN to us — callers must not treat it as a decline.
        return 0, {"error": {"code": "connection_failed", "message": str(exc)[:200]}}


def get_token(force: bool = False) -> str:
    if not force:
        tok = cache.get(_TOKEN_CACHE_KEY)
        if tok:
            return tok
    auth = base64.b64encode(
        f"{settings.PAYLOV_CONSUMER_KEY}:{settings.PAYLOV_CONSUMER_SECRET}".encode()
    ).decode()
    status, data = _raw_post(
        f"{_base()}/oauth2/token/",
        {
            "grant_type": "password",
            "username": settings.PAYLOV_API_USERNAME,
            "password": settings.PAYLOV_API_PASSWORD,
        },
        {"Authorization": f"Basic {auth}"},
    )
    ok = bool(data.get("access_token"))
    log_paylov(
        "out", "oauth2/token", ok=ok, http_status=status,
        request_body={"grant_type": "password", "username": settings.PAYLOV_API_USERNAME},
        response_body={"token_type": data.get("token_type"), "expires_in": data.get("expires_in")}
        if ok else data,
    )
    tok = data.get("access_token")
    if not tok:
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        raise PaylovError(err.get("code", "auth_failed"), err.get("message", "OAuth2 token error"), data, status)
    cache.set(_TOKEN_CACHE_KEY, tok, max(int(data.get("expires_in", 3600)) - 60, 60))
    return tok


def _api_post(
    path: str, body: dict[str, Any], *, payment=None, event: str | None = None,
    mask: bool = False, _retry: bool = True,
) -> dict[str, Any]:
    token = get_token()
    status, data = _raw_post(f"{_base()}/{path.lstrip('/')}", body, {"Authorization": f"Bearer {token}"})
    err = data.get("error") if isinstance(data, dict) else None
    log_paylov(
        "out", event or path, payment=payment, ok=(200 <= status < 300 and not err), http_status=status,
        request_body=_mask_card(body) if mask else body, response_body=data,
    )
    if status == 401 and _retry:  # token expired/invalid → refresh once
        get_token(force=True)
        return _api_post(path, body, payment=payment, event=event, mask=mask, _retry=False)
    if err:
        code = err.get("code", "error") if isinstance(err, dict) else "error"
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        raise PaylovError(code, msg, err.get("data") if isinstance(err, dict) else None, status)
    # Anything that is not an explicit 2xx is NOT a success — never let a
    # 5xx / odd body without an "error" key be mistaken for a confirmed call.
    if not (200 <= status < 300):
        raise PaylovError("http_error", f"Unexpected HTTP {status}", data, status)
    return data


def payment_without_registration(
    card_number: str, expire_date: str, amount_uzs: int, account: dict[str, Any], *, payment=None
) -> dict[str, Any]:
    """Create a guest (unregistered-card) payment. Returns transactionId; OTP is sent to the cardholder.

    ``amount_uzs`` is in SOM — per Paylov's "Payment Without Registration" docs
    ("1000 = 1 Thousand SUM"). Do NOT convert to tiyin.
    """
    body = {
        "cardNumber": card_number,
        "expireDate": expire_date,
        "amount": amount_uzs,
        "account": account,
    }
    return _api_post(
        "paymentWithoutRegistration/", body, payment=payment,
        event="paymentWithoutRegistration", mask=True,
    )


def confirm_payment(transaction_id: str, otp: str | None = None, *, payment=None) -> dict[str, Any]:
    """Confirm a payment with the OTP (or, without otp, trigger/resend the OTP)."""
    body: dict[str, Any] = {"transactionId": transaction_id}
    if otp:
        body["otp"] = otp
    return _api_post("confirmPayment/", body, payment=payment, event="confirmPayment")


def cancel_payment(transaction_id: str, *, payment=None) -> dict[str, Any]:
    return _api_post("payment/cancel/", {"transactionId": transaction_id}, payment=payment, event="payment/cancel")



# ── Subscribe API: saved cards + merchant-initiated payments ───────────────
# A transport-level failure means we do not know whether Paylov acted.
AMBIGUOUS_CODES = frozenset({"connection_failed", "http_error"})


def _api_call(
    method: str, path: str, *, body: dict[str, Any] | None = None, payment=None,
    event: str | None = None, mask: bool = False, _retry: bool = True,
) -> dict[str, Any]:
    """Like ``_api_post`` but for any HTTP method (GET/DELETE take the query
    string in ``path``). Same logging and the same strict success rule."""
    token = get_token()
    status, data = _raw_request(
        method, f"{_base()}/{path.lstrip('/')}", body, {"Authorization": f"Bearer {token}"}
    )
    err = data.get("error") if isinstance(data, dict) else None
    log_paylov(
        "out", event or path.split("?")[0], payment=payment,
        ok=(200 <= status < 300 and not err), http_status=status,
        request_body=(_mask_card(body) if mask else body) if body is not None else {"query": path.partition("?")[2]},
        response_body=data,
    )
    if status == 401 and _retry:
        get_token(force=True)
        return _api_call(method, path, body=body, payment=payment, event=event, mask=mask, _retry=False)
    if err:
        code = err.get("code", "error") if isinstance(err, dict) else "error"
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        raise PaylovError(code, msg, err.get("data") if isinstance(err, dict) else None, status)
    if not (200 <= status < 300):
        raise PaylovError("http_error", f"Unexpected HTTP {status}", data, status)
    return data


def create_user_card(user_id: str, card_number: str, expire_date: str) -> dict[str, Any]:
    """Start linking a card: Paylov texts an SMS code to the cardholder.
    Returns ``{cid, otpSentPhone}`` (possibly wrapped in ``result``)."""
    body = {"userId": user_id, "cardNumber": card_number, "expireDate": expire_date}
    return _api_call("POST", "userCard/createUserCard/", body=body, event="userCard/create", mask=True)


def confirm_user_card(cid: str, otp: str) -> dict[str, Any]:
    """Finish linking with the SMS code → ``result.card`` (cardId, masked number…)."""
    return _api_call(
        "POST", "userCard/confirmUserCardCreate/", body={"cardId": cid, "otp": otp},
        event="userCard/confirm",
    )


def delete_user_card(card_id: str) -> dict[str, Any]:
    from urllib.parse import quote

    return _api_call(
        "DELETE", f"userCard/deleteUserCard/?userCardId={quote(card_id)}", event="userCard/delete"
    )


def create_receipt(user_id: str, amount_uzs: int, account: dict[str, Any], *, payment=None) -> dict[str, Any]:
    """Create a payable transaction (amount in SOM). Charges nothing yet."""
    body = {"userId": user_id, "amount": amount_uzs, "account": account}
    return _api_call("POST", "receipts/create/", body=body, payment=payment, event="receipts/create")


def pay_receipt(transaction_id: str, card_id: str, user_id: str, *, payment=None) -> dict[str, Any]:
    """Charge a SAVED card for the transaction — no SMS code (merchant-initiated)."""
    body = {"transactionId": transaction_id, "cardId": card_id, "userId": user_id}
    return _api_call("POST", "receipts/pay/", body=body, payment=payment, event="receipts/pay")


def get_transaction(transaction_id: str, *, payment=None) -> dict[str, Any]:
    from urllib.parse import quote

    return _api_call(
        "GET", f"getTransactions/?transactionId={quote(transaction_id)}", payment=payment,
        event="getTransactions",
    )
