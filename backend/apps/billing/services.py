"""Billing engine — seat counting, invoice math, subscription state machine.

Pricing rules (master spec §4, executed from the Phase-4 task message):
* seat count   = ACTIVE operators of the company, counted at invoice time;
* period total = seats × price snapshot held on the Subscription;
* price changes apply NEXT period only: invoices for a completed period use
  the snapshot taken when that period started; the snapshot refreshes to the
  current PricingSetting only when the period rolls over.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import cast

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import OperatorProfile, User
from apps.companies.models import Company
from apps.core.models import AuditLog

from .models import (
    BillingNotification,
    DailyCharge,
    Invoice,
    InvoiceLine,
    MonthlyStatement,
    Payment,
    PricingSetting,
    Subscription,
)

PERIOD_DAYS = 30
GRACE_DAYS = 2  # unpaid statement blocks the account on day 3


class InvalidTransition(Exception):
    """Raised on a disallowed subscription state change."""


# trial → active → suspended ⇄ active; anything (except canceled) → canceled.
_ALLOWED: dict[str, set[str]] = {
    Subscription.Status.TRIAL: {
        Subscription.Status.ACTIVE,
        Subscription.Status.SUSPENDED,
        Subscription.Status.CANCELED,
    },
    Subscription.Status.ACTIVE: {Subscription.Status.SUSPENDED, Subscription.Status.CANCELED},
    Subscription.Status.SUSPENDED: {Subscription.Status.ACTIVE, Subscription.Status.CANCELED},
    Subscription.Status.CANCELED: set(),
}


def _transition(subscription: Subscription, new_status: str) -> None:
    if new_status not in _ALLOWED[subscription.status]:
        raise InvalidTransition(f"{subscription.status} → {new_status} is not allowed")
    subscription.status = new_status


def effective_price(company: Company) -> int:
    """Company-specific PricingSetting, else global row, else settings default."""
    row = (
        PricingSetting.objects.filter(company=company).first()
        or PricingSetting.objects.filter(company=None).first()
    )
    if row is not None:
        return row.price_per_operator_uzs
    return int(settings.DEFAULT_PRICE_PER_OPERATOR_UZS)


def effective_trial_days(company: Company | None = None) -> int:
    row = PricingSetting.objects.filter(company=None).first()
    if row is not None:
        return row.trial_days
    return int(settings.TRIAL_DAYS)


def seat_count(company: Company) -> int:
    count: int = OperatorProfile.all_objects.filter(company=company, is_active=True).count()
    return count


def monthly_total(company: Company, price: int | None = None) -> int:
    return seat_count(company) * (price if price is not None else effective_price(company))


def _audit(
    company: Company | None, action: str, actor: User | None = None, **changes: object
) -> None:
    AuditLog.objects.create(
        company=company,
        actor=actor,
        action=action,
        target_model="billing.Subscription",
        target_id=str(company.pk) if company else "",
        changes=dict(changes),
    )


@transaction.atomic
def activate(
    subscription: Subscription,
    *,
    now: datetime | None = None,
    actor: User | None = None,
    period_days: int = PERIOD_DAYS,
) -> Subscription:
    """trial/suspended → active. Starts a fresh paid period at current pricing."""
    now = now or timezone.now()
    _transition(subscription, Subscription.Status.ACTIVE)
    subscription.price_per_operator_uzs = effective_price(subscription.company)
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=period_days)
    subscription.save()

    subscription.company.status = Company.Status.ACTIVE
    subscription.company.save(update_fields=["status", "updated_at"])
    _audit(subscription.company, "subscription.activated", actor)
    return subscription


@transaction.atomic
def suspend(subscription: Subscription, *, reason: str, actor: User | None = None) -> Subscription:
    _transition(subscription, Subscription.Status.SUSPENDED)
    subscription.save(update_fields=["status", "updated_at"])
    subscription.company.status = Company.Status.SUSPENDED
    subscription.company.save(update_fields=["status", "updated_at"])
    _audit(subscription.company, "subscription.suspended", actor, reason=reason)
    return subscription


@transaction.atomic
def cancel(subscription: Subscription, *, actor: User | None = None) -> Subscription:
    _transition(subscription, Subscription.Status.CANCELED)
    subscription.save(update_fields=["status", "updated_at"])
    subscription.company.status = Company.Status.SUSPENDED
    subscription.company.save(update_fields=["status", "updated_at"])
    _audit(subscription.company, "subscription.canceled", actor)
    return subscription


@transaction.atomic
def generate_invoice(
    subscription: Subscription,
    *,
    period_start: datetime,
    period_end: datetime,
    now: datetime | None = None,
) -> Invoice:
    """Invoice the COMPLETED period at the subscription's price snapshot."""
    now = now or timezone.now()
    company = subscription.company
    seats = seat_count(company)
    unit_price = subscription.price_per_operator_uzs  # snapshot — NOT current pricing
    total = seats * unit_price

    invoice = Invoice.all_objects.create(
        company=company,
        subscription=subscription,
        status=Invoice.Status.PENDING,
        period_start=period_start.date(),
        period_end=period_end.date(),
        total_uzs=total,
        issued_at=now,
        due_at=now + timedelta(days=7),
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        description=(
            f"dooCall subscription {period_start.date()} – {period_end.date()}: "
            f"{seats} operator(s) × {unit_price} UZS"
        ),
        quantity=seats,
        unit_price_uzs=unit_price,
        amount_uzs=total,
    )
    _audit(company, "invoice.generated", total_uzs=total, seats=seats, number=invoice.number)
    return cast(Invoice, invoice)


@transaction.atomic
def roll_period(
    subscription: Subscription,
    *,
    now: datetime | None = None,
    period_days: int = PERIOD_DAYS,
) -> Invoice:
    """At period end: invoice the finished period, then start the next one.

    The NEW period picks up the CURRENT PricingSetting — this is exactly the
    "price changes apply next period only" rule.
    """
    now = now or timezone.now()
    if subscription.current_period_start is None or subscription.current_period_end is None:
        raise InvalidTransition("subscription has no active period to invoice")

    invoice = generate_invoice(
        subscription,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        now=now,
    )
    subscription.current_period_start = subscription.current_period_end
    subscription.current_period_end = subscription.current_period_end + timedelta(days=period_days)
    subscription.price_per_operator_uzs = effective_price(subscription.company)
    subscription.save(
        update_fields=[
            "current_period_start",
            "current_period_end",
            "price_per_operator_uzs",
            "updated_at",
        ]
    )
    return invoice


# ── Daily billing model ────────────────────────────────────────────────────
def notify(
    company: Company, kind: str, message: str, amount_uzs: int | None = None
) -> BillingNotification:
    return cast(
        BillingNotification,
        BillingNotification.all_objects.create(
            company=company, kind=kind, message=message, amount_uzs=amount_uzs
        ),
    )


def daily_rate(price_per_operator_uzs: int, day: date) -> int:
    """Monthly tariff spread over the actual days of that month."""
    days_in_month = calendar.monthrange(day.year, day.month)[1]
    return round(price_per_operator_uzs / days_in_month)


def accrue_operator_day(
    company: Company, operator: OperatorProfile, day: date
) -> DailyCharge | None:
    """Write ONE operator-day charge (idempotent). Trial/suspended = free."""
    if company.status != Company.Status.ACTIVE:
        return None
    price = effective_price(company)  # today's tariff — a change applies same day
    charge, _created = DailyCharge.all_objects.get_or_create(
        company=company,
        date=day,
        operator_name=operator.user_name,
        defaults={
            "operator": operator,
            "amount_uzs": daily_rate(price, day),
            "price_per_operator_uzs": price,
        },
    )
    return cast(DailyCharge, charge)


def accrue_company_day(company: Company, day: date) -> int:
    """Charge every ACTIVE operator of the company for ``day``."""
    if company.status != Company.Status.ACTIVE:
        return 0
    count = 0
    for operator in OperatorProfile.all_objects.filter(company=company, is_active=True):
        if accrue_operator_day(company, operator, day) is not None:
            count += 1
    return count


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _prev_month_start(day: date) -> date:
    return (day.replace(day=1) - timedelta(days=1)).replace(day=1)


def month_accrued(company: Company, month: date) -> int:
    month = _month_start(month)
    if month.month == 12:
        next_month = month.replace(year=month.year + 1, month=1)
    else:
        next_month = month.replace(month=month.month + 1)
    total = DailyCharge.all_objects.filter(
        company=company, date__gte=month, date__lt=next_month
    ).aggregate(s=Sum("amount_uzs"))["s"]
    return int(total or 0)


def _reactivate_if_clear(company: Company, now: datetime) -> None:
    """Bring a suspended company back once nothing is owed."""
    owes = (
        MonthlyStatement.all_objects.filter(company=company)
        .exclude(status=MonthlyStatement.Status.PAID)
        .exists()
    )
    if owes or company.status != Company.Status.SUSPENDED:
        return
    subscription = Subscription.all_objects.filter(company=company).first()
    if subscription is not None and subscription.status == Subscription.Status.SUSPENDED:
        activate(subscription, now=now)
    else:
        company.status = Company.Status.ACTIVE
        company.save(update_fields=["status", "updated_at"])


@transaction.atomic
def settle_statement(statement: MonthlyStatement, *, now: datetime) -> bool:
    """Deduct the statement from the balance if it covers the total."""
    company = Company.objects.select_for_update().get(pk=statement.company_id)
    if statement.status == MonthlyStatement.Status.PAID or statement.total_uzs == 0:
        if statement.status != MonthlyStatement.Status.PAID:
            statement.status = MonthlyStatement.Status.PAID
            statement.settled_at = now
            statement.save(update_fields=["status", "settled_at"])
        return True
    if company.balance_uzs < statement.total_uzs:
        return False
    company.balance_uzs -= statement.total_uzs
    company.save(update_fields=["balance_uzs", "updated_at"])
    statement.status = MonthlyStatement.Status.PAID
    statement.settled_at = now
    statement.save(update_fields=["status", "settled_at"])
    notify(
        company,
        BillingNotification.Kind.CHARGE_SETTLED,
        f"{statement.month:%Y-%m} oyi uchun {statement.total_uzs:,} UZS balansdan yechildi. "
        f"Qoldiq: {company.balance_uzs:,} UZS".replace(",", " "),
        statement.total_uzs,
    )
    _audit(company, "billing.statement_settled", total_uzs=statement.total_uzs)
    return True


def settle_month(company: Company, month: date, *, now: datetime) -> MonthlyStatement:
    """Create/refresh the statement for ``month`` and try to settle it."""
    month = _month_start(month)
    total = month_accrued(company, month)
    statement, _ = MonthlyStatement.all_objects.get_or_create(
        company=company, month=month, defaults={"total_uzs": total}
    )
    if statement.status != MonthlyStatement.Status.PAID and statement.total_uzs != total:
        statement.total_uzs = total
        statement.save(update_fields=["total_uzs"])
    if not settle_statement(statement, now=now) and statement.status == (
        MonthlyStatement.Status.PENDING
    ):
        notify(
            company,
            BillingNotification.Kind.PAYMENT_DUE,
            f"{month:%Y-%m} oyi uchun {statement.total_uzs:,} UZS to'lov qilish kerak. "
            f"{GRACE_DAYS} kun ichida to'lanmasa tizim bloklanadi.".replace(",", " "),
            statement.total_uzs,
        )
    return cast(MonthlyStatement, statement)


@transaction.atomic
def credit_balance(
    company: Company, amount_uzs: int, *, now: datetime, note: str = ""
) -> None:
    """Top up the balance and auto-settle unpaid statements (oldest first)."""
    company = Company.objects.select_for_update().get(pk=company.pk)
    company.balance_uzs += amount_uzs
    company.save(update_fields=["balance_uzs", "updated_at"])
    notify(
        company,
        BillingNotification.Kind.PAYMENT_RECEIVED,
        f"To'lov qabul qilindi: {amount_uzs:,} UZS. Balans: {company.balance_uzs:,} UZS".replace(
            ",", " "
        ),
        amount_uzs,
    )
    for statement in MonthlyStatement.all_objects.filter(company=company).exclude(
        status=MonthlyStatement.Status.PAID
    ).order_by("month"):
        if not settle_statement(statement, now=now):
            break
    company.refresh_from_db()
    _reactivate_if_clear(company, now)


@transaction.atomic
def refund_payment(
    payment: Payment, *, actor: User | None = None, now: datetime | None = None
) -> Payment:
    """Reverse an approved payment: mark rejected, DEBIT the balance and
    tell the client. (The admin returns the money outside the system.)"""
    now = now or timezone.now()
    if payment.status != Payment.Status.APPROVED:
        raise ValueError("only approved payments can be refunded")
    payment.status = Payment.Status.REJECTED  # refund marker (no new enum)
    payment.save(update_fields=["status"])
    company = Company.objects.select_for_update().get(pk=payment.company_id)
    company.balance_uzs -= payment.amount_uzs  # may go negative → visible debt
    company.save(update_fields=["balance_uzs", "updated_at"])
    notify(
        company,
        BillingNotification.Kind.PAYMENT_REFUNDED,
        f"To'lov bekor qilindi: {payment.amount_uzs:,} UZS balansdan yechildi. "
        f"Balans: {company.balance_uzs:,} UZS".replace(",", " "),
        payment.amount_uzs,
    )
    _audit(
        company,
        "payment.refunded",
        actor,
        amount_uzs=payment.amount_uzs,
        payment_id=payment.pk,
    )
    return payment


def run_overdue_enforcement(now: datetime) -> int:
    """Block companies whose statement stayed unpaid past the grace window."""
    today = now.date()
    blocked = 0
    unpaid = MonthlyStatement.all_objects.filter(
        status=MonthlyStatement.Status.PENDING
    ).select_related("company")
    for statement in unpaid:
        if statement.month.month == 12:
            due_from = statement.month.replace(year=statement.month.year + 1, month=1)
        else:
            due_from = statement.month.replace(month=statement.month.month + 1)
        if today < due_from + timedelta(days=GRACE_DAYS):
            continue
        statement.status = MonthlyStatement.Status.OVERDUE
        statement.save(update_fields=["status"])
        company = statement.company
        if company.status == Company.Status.ACTIVE:
            subscription = Subscription.all_objects.filter(company=company).first()
            if subscription is not None and subscription.status in (
                Subscription.Status.TRIAL,
                Subscription.Status.ACTIVE,
            ):
                suspend(subscription, reason="payment_overdue")
            else:
                company.status = Company.Status.SUSPENDED
                company.save(update_fields=["status", "updated_at"])
            notify(
                company,
                BillingNotification.Kind.BLOCKED,
                f"{statement.month:%Y-%m} oyi to'lovi kechikkani uchun tizim bloklandi. "
                f"To'lovdan so'ng avtomatik ochiladi ({statement.total_uzs:,} UZS)".replace(
                    ",", " "
                ),
                statement.total_uzs,
            )
            blocked += 1
    return blocked


@transaction.atomic
def apply_payment(
    payment: Payment,
    *,
    actor: User | None = None,
    now: datetime | None = None,
) -> Payment:
    """A successful payment: mark approved, settle invoice, (re)activate company.

    Used by BOTH the admin manual-approval action and provider webhooks.
    """
    now = now or timezone.now()
    if payment.status == Payment.Status.APPROVED:
        return payment  # idempotent — webhook retries must not double-extend

    payment.status = Payment.Status.APPROVED
    payment.approved_by = actor
    payment.approved_at = now
    payment.save(update_fields=["status", "approved_by", "approved_at"])

    if payment.invoice and payment.invoice.status != Invoice.Status.PAID:
        payment.invoice.status = Invoice.Status.PAID
        payment.invoice.save(update_fields=["status"])

    subscription = Subscription.all_objects.filter(company=payment.company).first()
    if subscription is not None:
        if subscription.status in (
            Subscription.Status.TRIAL,
            Subscription.Status.SUSPENDED,
        ):
            activate(subscription, now=now, actor=actor)
        else:
            # Already active → extend the running period by one billing cycle.
            base = subscription.current_period_end or now
            subscription.current_period_end = max(base, now) + timedelta(days=PERIOD_DAYS)
            subscription.save(update_fields=["current_period_end", "updated_at"])
            subscription.company.status = Company.Status.ACTIVE
            subscription.company.save(update_fields=["status", "updated_at"])

    _audit(
        payment.company,
        "payment.applied",
        actor,
        provider=payment.provider,
        amount_uzs=payment.amount_uzs,
        payment_id=payment.pk,
    )

    # Daily-billing model: every approved payment tops up the prepaid balance
    # and auto-settles unpaid monthly statements (unblocking if cleared).
    credit_balance(payment.company, payment.amount_uzs, now=now)

    # Cashback engine (A.5): one idempotent accrual per successful payment,
    # regardless of provider (manual admin approval, Payme, Click).
    from apps.partners.services import accrue_cashback

    accrue_cashback(payment, now=now)
    return payment
