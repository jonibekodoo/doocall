"""Saved cards + automatic top-up (Paylov Subscribe API).

The money rule is the same as for a manual card payment and is enforced in
exactly one place (:func:`charge_saved_card`): **the balance is credited only
after Paylov confirmed the charge**. Three outcomes are kept strictly apart:

* confirmed  → ``apply_payment`` (credits the balance, reactivates if needed);
* declined   → Payment FAILED, nothing credited, the caller decides on retry;
* unknown    → (timeout / 5xx) Payment stays PENDING, nothing credited and
  **no second attempt** until :func:`reconcile_pending` learns the truth from
  Paylov — an unknown outcome must never turn into a double charge.

Automatic attempts additionally carry a unique per-company-per-day
``idempotency_key`` so two workers can never both charge the same day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company
from apps.core.models import AuditLog

from . import paylov_api, services
from .models import (
    AutoPaySettings,
    BillingNotification,
    Payment,
    PaymentProviderConfig,
    SavedCard,
)

logger = logging.getLogger(__name__)

MAX_FAIL_STREAK = 3          # consecutive failed days before auto-pay turns itself off
DEFAULT_LIMIT_MONTHS = 2     # default 30-day cap = this many months of service
MIN_AMOUNT_UZS = 1000
MAX_CARDS = 5
PENDING_HOLD = timedelta(days=3)      # an unknown-outcome charge blocks new attempts this long
RECONCILE_GIVE_UP = timedelta(hours=24)

# The card itself is unusable — retrying tomorrow cannot help.
HARD_CARD_ERRORS = frozenset(
    {
        "card_not_found",
        "card_expired",
        "card_is_blocked",
        "card_not_active",
        "invalid_card_token",
        "sms_not_active",
    }
)
_ALREADY_PAID = ("transaction_already_payed", "already_confirmed")


class ChargeFailed(Exception):
    """Paylov declined (or we could not even create the transaction)."""

    def __init__(self, code: str, payment: Payment | None = None):
        self.code = code
        self.payment = payment
        super().__init__(code)


class ChargePending(Exception):
    """Outcome unknown — nothing credited, do not retry until reconciled."""

    def __init__(self, payment: Payment):
        self.payment = payment
        super().__init__("pending")


class AlreadyAttempted(Exception):
    """An automatic attempt with this idempotency key already exists."""


def paylov_user_id(company: Company) -> str:
    """Stable id of the company on Paylov's side (cards are grouped by it)."""
    return f"doocall-company-{company.pk}"


def platform_enabled() -> bool:
    """Paylov must be on, configured, and the automatic-charge switch not pulled."""
    from django.conf import settings as dj

    cfg = PaymentProviderConfig.objects.filter(provider="paylov").first()
    return bool(
        cfg
        and cfg.is_enabled
        and cfg.autopay_enabled
        and dj.PAYLOV_CONSUMER_KEY
        and dj.PAYLOV_API_USERNAME
    )


def cards_available() -> bool:
    """Saved cards (linking, one-click pay) need Paylov on — not the auto switch."""
    from django.conf import settings as dj

    cfg = PaymentProviderConfig.objects.filter(provider="paylov", is_enabled=True).first()
    return bool(cfg and dj.PAYLOV_CONSUMER_KEY and dj.PAYLOV_API_USERNAME)


def get_settings(company: Company) -> AutoPaySettings:
    row, _ = AutoPaySettings.all_objects.get_or_create(company=company)
    return row


# ── cards ─────────────────────────────────────────────────────────────────
def start_card_link(company: Company, card_number: str, expire: str, user: User | None) -> tuple[SavedCard, str]:
    """Ask Paylov to text the SMS code; keep an unconfirmed row holding the cid."""
    SavedCard.all_objects.filter(
        company=company, is_confirmed=False, created_at__lt=timezone.now() - timedelta(days=1)
    ).delete()
    resp = paylov_api.create_user_card(paylov_user_id(company), card_number, expire)
    data = resp.get("result") or resp
    cid = data.get("cid") or data.get("cardId")
    if not cid:
        raise paylov_api.PaylovError("no_card_id", "Paylov returned no card id", resp)
    card = SavedCard.all_objects.create(
        company=company,
        paylov_card_id=str(cid),
        paylov_user_id=paylov_user_id(company),
        masked_number=("*" * 12 + card_number[-4:]),
        expire=expire,
        created_by=user,
    )
    return card, str(data.get("otpSentPhone") or "")


def confirm_card_link(card: SavedCard, otp: str) -> SavedCard:
    resp = paylov_api.confirm_user_card(card.paylov_card_id, otp)
    info = ((resp.get("result") or {}).get("card")) or {}
    if not info.get("cardId"):
        # A 2xx without the card object is not a confirmed link.
        raise paylov_api.PaylovError("card_not_confirmed", "Paylov did not confirm the card", resp)
    card.paylov_card_id = str(info["cardId"])
    card.masked_number = str(info.get("number") or card.masked_number)[:24]
    card.owner = str(info.get("owner") or "")[:120]
    card.vendor = str(info.get("vendor") or info.get("processing") or "")[:32]
    card.expire = str(info.get("expireDate") or card.expire)[:4]
    card.is_confirmed = True
    card.is_active = True
    card.confirmed_at = timezone.now()
    card.save()
    # The same physical card linked again replaces its older row.
    SavedCard.all_objects.filter(
        company=card.company, paylov_card_id=card.paylov_card_id
    ).exclude(pk=card.pk).update(is_active=False)
    return card


def remove_card(card: SavedCard, *, actor: User | None = None) -> None:
    """Unlink at Paylov (best effort) and locally; auto-pay using it stops."""
    try:
        paylov_api.delete_user_card(card.paylov_card_id)
    except paylov_api.PaylovError as exc:
        if exc.code != "card_not_found":
            logger.warning("paylov card delete failed for %s: %s", card.pk, exc)
    card.is_active = False
    card.save(update_fields=["is_active"])
    settings_row = AutoPaySettings.all_objects.filter(company=card.company, card=card).first()
    if settings_row is not None:
        _disable(settings_row, "card_removed", notify=False)
    AuditLog.objects.create(
        company=card.company, actor=actor, action="billing.card_removed",
        target_model="billing.SavedCard", target_id=str(card.pk), changes={"card": card.label},
    )


# ── the one place that charges a saved card ───────────────────────────────
def charge_saved_card(
    company: Company,
    card: SavedCard,
    amount_uzs: int,
    *,
    is_auto: bool,
    actor: User | None = None,
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> Payment:
    """Charge ``card`` and credit the balance — only on Paylov's confirmation.

    Raises :class:`ChargeFailed` (declined, nothing credited),
    :class:`ChargePending` (outcome unknown, nothing credited) or
    :class:`AlreadyAttempted` (duplicate automatic attempt)."""
    if not card.usable or card.company_id != company.pk:
        raise ChargeFailed("card_not_active")
    if amount_uzs < MIN_AMOUNT_UZS:
        raise ChargeFailed("amount_invalid")
    user_id = card.paylov_user_id or paylov_user_id(company)

    try:
        with transaction.atomic():  # savepoint: a duplicate key must not poison the caller's tx
            payment = Payment.all_objects.create(
                company=company,
                provider=Payment.Provider.PAYLOV,
                amount_uzs=amount_uzs,
                is_auto=is_auto,
                saved_card=card,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        raise AlreadyAttempted(idempotency_key or "") from None

    def fail(code: str) -> ChargeFailed:
        payment.status = Payment.Status.FAILED
        payment.failure_code = code[:64]
        payment.save(update_fields=["status", "failure_code"])
        return ChargeFailed(code, payment)

    # 1) create the transaction — this never moves money, so any error is final
    try:
        resp = paylov_api.create_receipt(
            user_id, amount_uzs, {"order_id": str(payment.pk)}, payment=payment
        )
    except paylov_api.PaylovError as exc:
        raise fail(exc.code) from None
    txn = (resp.get("result") or {}).get("transactionId") or resp.get("transactionId")
    if not txn:
        raise fail("no_transaction")
    payment.external_id = str(txn)
    payment.save(update_fields=["external_id"])

    # 2) charge the saved card
    confirmed = False
    try:
        resp = paylov_api.pay_receipt(payment.external_id, card.paylov_card_id, user_id, payment=payment)
    except paylov_api.PaylovError as exc:
        if exc.code in _ALREADY_PAID:
            confirmed = True  # Paylov itself says the money was taken
        elif exc.code in paylov_api.AMBIGUOUS_CODES:
            payment.failure_code = exc.code[:64]
            payment.save(update_fields=["failure_code"])
            raise ChargePending(payment) from None
        else:
            raise fail(exc.code) from None
    else:
        # A 2xx without "result" is NOT a completed payment — never credit on it.
        confirmed = bool(resp.get("result"))
        if not confirmed:
            payment.failure_code = "no_result"
            payment.save(update_fields=["failure_code"])
            raise ChargePending(payment)

    _credit(payment, actor=actor, now=now)
    return payment


def _credit(payment: Payment, *, actor: User | None, now: datetime | None) -> None:
    """Lock the row so concurrent paths can never credit the same payment twice."""
    with transaction.atomic():
        locked = Payment.all_objects.select_for_update().get(pk=payment.pk)
        if locked.status != Payment.Status.APPROVED:
            services.apply_payment(locked, actor=actor, now=now)
    payment.refresh_from_db()


def _is_paid(txn_id: str, data: dict[str, Any], amount_uzs: int) -> bool:
    """Does Paylov's transaction register list this transaction as a payment
    of the expected amount? (Unpaid receipts are not listed.)"""
    rows = ((data.get("result") or {}).get("transactions")) or []
    for row in rows:
        if str(row.get("id")) == txn_id and int(row.get("amount") or 0) == int(amount_uzs):
            return True
    return False


def reconcile_pending(now: datetime | None = None) -> int:
    """Resolve unknown-outcome saved-card charges by asking Paylov.

    Listed as paid → credit. Not listed after 24h → mark FAILED (nothing was
    taken). In between we keep waiting — and keep auto-pay on hold."""
    now = now or timezone.now()
    resolved = 0
    pending = Payment.all_objects.filter(
        provider=Payment.Provider.PAYLOV,
        status=Payment.Status.PENDING,
        saved_card__isnull=False,
    ).exclude(external_id="")
    for payment in pending:
        try:
            data = paylov_api.get_transaction(payment.external_id, payment=payment)
        except paylov_api.PaylovError:
            continue
        if _is_paid(payment.external_id, data, payment.amount_uzs):
            _credit(payment, actor=None, now=now)
            resolved += 1
        elif now - payment.created_at > RECONCILE_GIVE_UP:
            payment.status = Payment.Status.FAILED
            payment.failure_code = payment.failure_code or "unconfirmed"
            payment.save(update_fields=["status", "failure_code"])
            resolved += 1
    return resolved


# ── automatic top-up ──────────────────────────────────────────────────────
@dataclass
class Quote:
    """What auto-pay would do for a company right now."""

    due: bool               # balance covers less than one day of service
    amount_uzs: int         # what would be charged
    month_cost_uzs: int
    limit_uzs: int          # 30-day cap in force
    spent_30d_uzs: int
    over_limit: bool


def monthly_cost(company: Company) -> int:
    return services.seat_count(company) * services.effective_price(company)


def spent_last_30d(company: Company, now: datetime) -> int:
    return int(
        Payment.all_objects.filter(
            company=company, is_auto=True, status=Payment.Status.APPROVED,
            approved_at__gte=now - timedelta(days=30),
        ).aggregate(s=Sum("amount_uzs"))["s"]
        or 0
    )


def quote(company: Company, settings_row: AutoPaySettings, now: datetime | None = None) -> Quote:
    now = now or timezone.now()
    month_cost = monthly_cost(company)
    burn = services.seat_count(company) * services.daily_rate(
        services.effective_price(company), now.date()
    )
    base = month_cost
    if settings_row.amount_mode == AutoPaySettings.AmountMode.FIXED and settings_row.fixed_amount_uzs:
        base = int(settings_row.fixed_amount_uzs)
    # Always enough to clear a negative balance and cover the next day.
    amount = max(base, burn - company.balance_uzs, MIN_AMOUNT_UZS)
    limit = int(settings_row.monthly_limit_uzs or DEFAULT_LIMIT_MONTHS * month_cost)
    spent = spent_last_30d(company, now)
    return Quote(
        due=burn > 0 and company.balance_uzs < burn,
        amount_uzs=int(amount),
        month_cost_uzs=month_cost,
        limit_uzs=limit,
        spent_30d_uzs=spent,
        over_limit=amount > limit - spent,
    )


def _suspended_by_staff(company: Company) -> bool:
    """A company an administrator suspended by hand must not be auto-charged."""
    last = (
        AuditLog.objects.filter(company=company, action="subscription.suspended")
        .order_by("-id")
        .first()
    )
    return bool(last and last.actor_id)


def _notify_once_today(company: Company, message: str, now: datetime) -> None:
    kind = BillingNotification.Kind.AUTOPAY_FAILED
    if BillingNotification.all_objects.filter(
        company=company, kind=kind, message=message, created_at__date=now.date()
    ).exists():
        return
    services.notify(company, kind, message)


def _disable(settings_row: AutoPaySettings, reason: str, *, notify: bool = True) -> None:
    settings_row.is_enabled = False
    settings_row.disabled_reason = reason[:64]
    settings_row.save(update_fields=["is_enabled", "disabled_reason", "updated_at"])
    if notify:
        services.notify(
            settings_row.company,
            BillingNotification.Kind.AUTOPAY_FAILED,
            f"Avto to'lov o'chirildi: {error_text(reason)}. "
            "Sozlamalar → Litsenziya bo'limida qayta yoqishingiz mumkin.",
        )


def error_text(code: str, lang: str = "uz") -> str:
    """Human text for a stable error code (reuses the cabinet's Paylov table)."""
    own = {
        "limit_reached": {
            "uz": "oylik limitga yetildi",
            "ru": "достигнут месячный лимит",
            "en": "the monthly limit was reached",
        },
        "card_removed": {"uz": "karta olib tashlangan", "ru": "карта удалена", "en": "the card was removed"},
        "too_many_failures": {
            "uz": "ketma-ket 3 kun to'lov o'tmadi",
            "ru": "платёж не прошёл 3 дня подряд",
            "en": "the charge failed 3 days in a row",
        },
        "pending_check": {
            "uz": "oldingi to'lov natijasi tekshirilmoqda",
            "ru": "проверяется результат предыдущего платежа",
            "en": "the previous charge is being verified",
        },
        "unconfirmed": {
            "uz": "to'lov tasdiqlanmadi",
            "ru": "платёж не подтверждён",
            "en": "the charge was not confirmed",
        },
    }
    if not code:
        return ""
    if code in own:
        return own[code].get(lang) or own[code]["uz"]
    from apps.web.views_billing import _CODE_ALIASES, _MSG  # localized Paylov messages

    key = _CODE_ALIASES.get(code, code)
    msg = _MSG.get(key) or _MSG["generic"]
    return msg.get(lang) or msg["uz"]


def attempt_autopay(settings_row: AutoPaySettings, now: datetime) -> str:
    """One company's nightly check. Returns a short outcome tag (for logs/tests)."""
    company = settings_row.company
    card = settings_row.card
    if not settings_row.is_enabled:
        return "off"
    if card is None or not card.usable:
        _disable(settings_row, "card_not_active")
        return "disabled"
    if company.status == Company.Status.TRIAL:
        return "trial"
    if company.status == Company.Status.SUSPENDED and _suspended_by_staff(company):
        return "staff_suspended"

    q = quote(company, settings_row, now)
    if not q.due:
        return "not_due"
    # An earlier charge with an unknown outcome → never risk a second one.
    if Payment.all_objects.filter(
        company=company, is_auto=True, status=Payment.Status.PENDING,
        created_at__gte=now - PENDING_HOLD,
    ).exists():
        _mark(settings_row, now, "pending", "pending_check")
        return "held"
    if q.over_limit:
        _mark(settings_row, now, "failed", "limit_reached")
        _notify_once_today(
            company,
            f"Avto to'lov bajarilmadi: oylik limitga yetildi "
            f"({q.spent_30d_uzs:,} / {q.limit_uzs:,} UZS). Balansni qo'lda to'ldiring "
            "yoki limitni oshiring.".replace(",", " "),
            now,
        )
        return "limit"

    key = f"auto:{company.pk}:{now.date().isoformat()}"
    try:
        charge_saved_card(
            company, card, q.amount_uzs, is_auto=True, idempotency_key=key, now=now
        )
    except AlreadyAttempted:
        return "already"
    except ChargePending:
        _mark(settings_row, now, "pending", "pending_check")
        return "pending"
    except ChargeFailed as exc:
        settings_row.fail_streak += 1
        _mark(settings_row, now, "failed", exc.code, save_streak=True)
        if exc.code in HARD_CARD_ERRORS:
            card.is_active = False
            card.save(update_fields=["is_active"])
            _disable(settings_row, exc.code)
            return "disabled"
        if settings_row.fail_streak >= MAX_FAIL_STREAK:
            _disable(settings_row, "too_many_failures")
            return "disabled"
        services.notify(
            company,
            BillingNotification.Kind.AUTOPAY_FAILED,
            f"Avto to'lov o'tmadi ({card.label}): {error_text(exc.code)}. "
            f"Ertaga qayta uriniladi ({settings_row.fail_streak}/{MAX_FAIL_STREAK}).",
            q.amount_uzs,
        )
        return "failed"

    settings_row.fail_streak = 0
    _mark(settings_row, now, "ok", "", save_streak=True)
    AuditLog.objects.create(
        company=company, action="billing.autopay_charged",
        target_model="billing.AutoPaySettings", target_id=str(settings_row.pk),
        changes={"amount_uzs": q.amount_uzs, "card": card.label},
    )
    return "charged"


def _mark(
    settings_row: AutoPaySettings, now: datetime, status: str, error: str, *, save_streak: bool = False
) -> None:
    settings_row.last_attempt_at = now
    settings_row.last_status = status
    settings_row.last_error = error[:64]
    fields = ["last_attempt_at", "last_status", "last_error", "updated_at"]
    if save_streak:
        fields.append("fail_streak")
    settings_row.save(update_fields=fields)


def run_autopay(now: datetime | None = None) -> dict[str, int]:
    """Nightly sweep (after the daily deduction): reconcile, then top up."""
    now = now or timezone.now()
    outcomes: dict[str, int] = {}
    if not cards_available():
        return outcomes
    outcomes["reconciled"] = reconcile_pending(now)
    if not platform_enabled():
        return outcomes
    rows = AutoPaySettings.all_objects.filter(is_enabled=True).select_related("company", "card")
    for settings_row in rows:
        try:
            tag = attempt_autopay(settings_row, now)
        except Exception:  # noqa: BLE001 - one company must never stop the sweep
            logger.exception("autopay failed for company %s", settings_row.company_id)
            tag = "error"
        outcomes[tag] = outcomes.get(tag, 0) + 1
    return outcomes
