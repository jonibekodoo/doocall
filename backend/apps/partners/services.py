"""Cashback engine (A.5) + platform-role helpers + reassignment service."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.billing.models import Payment
from apps.companies.models import Company
from apps.core.models import AuditLog

from .models import (
    INTEGRATOR_PERMS,
    PLATFORM_ADMIN_PERMS,
    ROLE_INTEGRATOR,
    ROLE_PLATFORM_ADMIN,
    ROLE_SUPERADMIN,
    SUPERADMIN_PERMS,
    CashbackAccrual,
    Integrator,
    PayoutRequest,
    get_platform_settings,
)

_ROLE_PERMS = {
    ROLE_SUPERADMIN: SUPERADMIN_PERMS,
    ROLE_PLATFORM_ADMIN: PLATFORM_ADMIN_PERMS,
    ROLE_INTEGRATOR: INTEGRATOR_PERMS,
}


def get_platform_role(name: str) -> Role:
    """Platform-level Role rows (company=NULL) with the A.1 permission sets."""
    role, _ = Role.objects.get_or_create(
        company=None, name=name, defaults={"permissions": _ROLE_PERMS[name]}
    )
    return role


def role_name(user: object) -> str:
    """Effective role for routing/guards: platform role > company role."""
    if not isinstance(user, User) or not user.is_authenticated:
        return "anonymous"
    if user.role and user.role.company_id is None and user.role.name in _ROLE_PERMS:
        return user.role.name
    if user.is_superuser:
        return ROLE_SUPERADMIN
    if user.company_id is not None:
        return "company_admin" if user.is_company_admin else "company_user"
    return "none"


def portal_for(role: str) -> str:
    return {
        ROLE_SUPERADMIN: "admin",
        ROLE_PLATFORM_ADMIN: "admin",
        ROLE_INTEGRATOR: "partner",
    }.get(role, "cabinet")


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar-correct month addition (no external deps)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp the day (e.g. Jan 31 + 1m → Feb 28/29).
    day = min(
        moment.day,
        [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return moment.replace(year=year, month=month, day=day)


@transaction.atomic
def accrue_cashback(payment: Payment, *, now: datetime | None = None) -> CashbackAccrual | None:
    """Create the accrual for a successful payment — idempotent (A.5).

    Rules: company must be bound to an ACTIVE integrator; the payment must
    fall within the company's first ``cashback_months_limit`` months; percent
    is snapshotted (override beats global default). Works identically for
    manual / Payme / Click because ALL providers converge on apply_payment.
    """
    now = now or timezone.now()
    company: Company = payment.company
    integrator = company.integrator
    if integrator is None or integrator.status != Integrator.Status.ACTIVE:
        return None

    existing = CashbackAccrual.objects.filter(payment=payment).first()
    if existing is not None:
        return existing  # idempotent: second processing returns the same row

    settings_row = get_platform_settings()
    cutoff = add_months(company.created_at, settings_row.cashback_months_limit)
    effective_at = payment.approved_at or now
    if effective_at >= cutoff:
        return None  # months-limit exceeded — no accrual

    percent = integrator.effective_percent
    amount = int(
        (Decimal(payment.amount_uzs) * percent / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    accrual = CashbackAccrual.objects.create(
        payment=payment,
        integrator=integrator,
        company=company,
        percent=percent,
        amount_uzs=amount,
    )
    AuditLog.objects.create(
        company=company,
        action="cashback.accrued",
        target_model="partners.CashbackAccrual",
        target_id=str(accrual.pk),
        changes={"amount_uzs": amount, "percent": str(percent), "payment_id": payment.pk},
    )
    return accrual


@transaction.atomic
def reverse_cashback(payment: Payment, *, now: datetime | None = None) -> CashbackAccrual | None:
    """Refunded payment → reverse its accrual (idempotent)."""
    now = now or timezone.now()
    accrual = CashbackAccrual.objects.filter(payment=payment).first()
    if accrual is None or accrual.status == CashbackAccrual.Status.REVERSED:
        return accrual
    accrual.status = CashbackAccrual.Status.REVERSED
    accrual.reversed_at = now
    accrual.save(update_fields=["status", "reversed_at"])
    AuditLog.objects.create(
        company=accrual.company,
        action="cashback.reversed",
        target_model="partners.CashbackAccrual",
        target_id=str(accrual.pk),
        changes={"payment_id": payment.pk},
    )
    return accrual


@transaction.atomic
def reassign_integrator(
    company: Company, new_integrator: Integrator | None, *, actor: User
) -> Company:
    """Superadmin-only rebinding. Existing accruals stay with the OLD owner."""
    old_id = company.integrator_id
    company._allow_integrator_change = True
    try:
        company.integrator = new_integrator
        company.save(update_fields=["integrator", "updated_at"])
    finally:
        company._allow_integrator_change = False
    AuditLog.objects.create(
        company=company,
        actor=actor,
        action="company.integrator_reassigned",
        target_model="companies.Company",
        target_id=str(company.pk),
        changes={"from": old_id, "to": new_integrator.pk if new_integrator else None},
    )
    return company


# ── Payout lifecycle ────────────────────────────────────────────────────────
class PayoutError(Exception):
    pass


@transaction.atomic
def request_payout(integrator: Integrator, amount_uzs: int, *, note: str = "") -> PayoutRequest:
    if amount_uzs <= 0:
        raise PayoutError("amount must be positive")
    minimum = get_platform_settings().min_payout_uzs
    if amount_uzs < minimum:
        raise PayoutError(f"amount below the minimum of {minimum} UZS")
    if amount_uzs > integrator.balance_uzs:
        raise PayoutError("amount exceeds available balance")
    payout = PayoutRequest.objects.create(integrator=integrator, amount_uzs=amount_uzs, note=note)
    AuditLog.objects.create(
        action="payout.requested",
        target_model="partners.PayoutRequest",
        target_id=str(payout.pk),
        changes={"integrator_id": integrator.pk, "amount_uzs": amount_uzs},
    )
    return payout


@transaction.atomic
def process_payout(
    payout: PayoutRequest, new_status: str, *, actor: User, note: str = ""
) -> PayoutRequest:
    if not payout.can_transition(new_status):
        raise PayoutError(f"{payout.status} → {new_status} is not allowed")
    payout.status = new_status
    payout.processed_by = actor
    payout.processed_at = timezone.now()
    if note:
        payout.note = note
    payout.save()

    if new_status == PayoutRequest.Status.PAID:
        _allocate_accruals(payout)

    AuditLog.objects.create(
        actor=actor,
        action=f"payout.{new_status}",
        target_model="partners.PayoutRequest",
        target_id=str(payout.pk),
        changes={"amount_uzs": payout.amount_uzs},
    )
    return payout


def _allocate_accruals(payout: PayoutRequest) -> None:
    """Mark oldest accrued rows as paid_out up to the payout amount."""
    remaining = payout.amount_uzs
    accruals = (
        CashbackAccrual.objects.select_for_update()
        .filter(integrator=payout.integrator, status=CashbackAccrual.Status.ACCRUED)
        .order_by("created_at")
    )
    for accrual in accruals:
        if remaining <= 0:
            break
        accrual.status = CashbackAccrual.Status.PAID_OUT
        accrual.payout = payout
        accrual.save(update_fields=["status", "payout"])
        remaining -= accrual.amount_uzs


def monthly_accrual_series(integrator: Integrator, months: int = 12) -> list[dict[str, Any]]:
    """Last N calendar months of accrual sums (SQL-side grouping)."""
    from django.db.models.functions import TruncMonth

    since = add_months(timezone.now(), -(months - 1)).replace(day=1)
    rows = (
        CashbackAccrual.objects.filter(integrator=integrator, created_at__gte=since)
        .exclude(status=CashbackAccrual.Status.REVERSED)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("amount_uzs"))
        .order_by("month")
    )
    by_month = {row["month"].strftime("%Y-%m"): int(row["total"]) for row in rows}
    series = []
    cursor = since
    now = timezone.now()
    while cursor <= now:
        key = cursor.strftime("%Y-%m")
        series.append({"month": key, "amount_uzs": by_month.get(key, 0)})
        cursor = add_months(cursor, 1)
    return series
