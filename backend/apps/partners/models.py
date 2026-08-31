"""Integrator (partner) entities + cashback engine models (Addendum A.2).

NOTE: ADDENDUM_admin_integrator.md is not present in this repo (verified by
search); the model set below implements the A.1/A.2/A.5 requirements as
inlined in the Phase-10 brief.
"""

from __future__ import annotations

import secrets
import string
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models, transaction

# ── Platform role names (A.1) ───────────────────────────────────────────────
ROLE_SUPERADMIN = "superadmin"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_INTEGRATOR = "integrator"
PLATFORM_ROLES = (ROLE_SUPERADMIN, ROLE_PLATFORM_ADMIN, ROLE_INTEGRATOR)

# Permission sets: superadmin ⊃ platform_admin. platform_admin explicitly
# lacks: platform settings, admin-user CRUD, cashback overrides, payouts,
# impersonation (the brief's exclusion list).
PLATFORM_ADMIN_PERMS = [
    "platform.dashboard",
    "platform.companies.manage",
    "platform.payments.approve",
    "platform.integrators.manage",
    "platform.audit.view",
]
SUPERADMIN_PERMS = PLATFORM_ADMIN_PERMS + [
    "platform.settings.manage",
    "platform.admins.manage",
    "platform.cashback.override",
    "platform.payouts.manage",
    "platform.impersonate",
]
INTEGRATOR_PERMS = ["partner.portal"]


def _referral_code() -> str:
    """8-char unambiguous referral code, e.g. 'K7KJ2M9Q'."""
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1L")
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Integrator(models.Model):
    """A partner who brings companies and earns cashback on their payments."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="integrator_profile"
    )
    name = models.CharField(max_length=200, help_text="Person or organisation name")
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    referral_code = models.CharField(max_length=12, unique=True, default=_referral_code)
    # NULL → use PlatformSetting.default_cashback_percent.
    cashback_percent_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    # Payout destination (card / bank requisites) — free-form per A.2.
    payout_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.referral_code})"

    @property
    def effective_percent(self) -> Decimal:
        if self.cashback_percent_override is not None:
            return Decimal(str(self.cashback_percent_override))
        return Decimal(str(get_platform_settings().default_cashback_percent))

    @property
    def balance_uzs(self) -> int:
        """Available balance: accrued − payouts that hold funds.

        Rejected payouts release their hold; reversed accruals never count;
        paid_out accruals were consumed by a paid payout.
        """
        accrued = (
            self.accruals.filter(status=CashbackAccrual.Status.ACCRUED).aggregate(
                s=models.Sum("amount_uzs")
            )["s"]
            or 0
        )
        held = (
            self.payout_requests.filter(
                status__in=[PayoutRequest.Status.PENDING, PayoutRequest.Status.APPROVED]
            ).aggregate(s=models.Sum("amount_uzs"))["s"]
            or 0
        )
        return int(accrued) - int(held)


class PlatformSetting(models.Model):
    """Singleton platform knobs — history-tracked like PricingSetting."""

    default_cashback_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    cashback_months_limit = models.PositiveSmallIntegerField(
        default=12, help_text="Accrue cashback only for the company's first N months"
    )
    min_payout_uzs = models.PositiveBigIntegerField(
        default=50000, help_text="Minimum payout request amount"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    _TRACKED = ("default_cashback_percent", "cashback_months_limit")

    def __str__(self) -> str:
        return f"cashback {self.default_cashback_percent}% / {self.cashback_months_limit}m"

    def save(self, *args: Any, **kwargs: Any) -> None:
        old = PlatformSetting.objects.filter(pk=self.pk).first() if self.pk else None
        changed = old is None or any(getattr(old, f) != getattr(self, f) for f in self._TRACKED)
        with transaction.atomic():
            super().save(*args, **kwargs)
            if changed:
                PlatformSettingHistory.objects.create(
                    setting=self,
                    default_cashback_percent=self.default_cashback_percent,
                    cashback_months_limit=self.cashback_months_limit,
                    changed_by=self.updated_by,
                )


class PlatformSettingHistory(models.Model):
    setting = models.ForeignKey(PlatformSetting, on_delete=models.CASCADE, related_name="history")
    default_cashback_percent = models.DecimalField(max_digits=5, decimal_places=2)
    cashback_months_limit = models.PositiveSmallIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.default_cashback_percent}% @ {self.changed_at:%Y-%m-%d}"


def get_platform_settings() -> PlatformSetting:
    row = PlatformSetting.objects.first()
    if row is None:
        row = PlatformSetting()
        row.save()
    return row


class CashbackAccrual(models.Model):
    """One accrual per successful payment (A.5) — percent snapshotted."""

    class Status(models.TextChoices):
        ACCRUED = "accrued", "Accrued"
        REVERSED = "reversed", "Reversed (refund)"
        PAID_OUT = "paid_out", "Paid out"

    payment = models.OneToOneField(  # ← the idempotency anchor
        "billing.Payment", on_delete=models.CASCADE, related_name="cashback_accrual"
    )
    integrator = models.ForeignKey(Integrator, on_delete=models.CASCADE, related_name="accruals")
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="cashback_accruals"
    )
    percent = models.DecimalField(max_digits=5, decimal_places=2)  # snapshot
    amount_uzs = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACCRUED)
    payout = models.ForeignKey(
        "partners.PayoutRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="allocated_accruals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["integrator", "status", "-created_at"]),
            models.Index(fields=["company", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.amount_uzs} UZS ({self.percent}%) [{self.status}]"


class PayoutRequest(models.Model):
    """Integrator withdrawal request — pending → approved → paid | rejected."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    integrator = models.ForeignKey(
        Integrator, on_delete=models.CASCADE, related_name="payout_requests"
    )
    amount_uzs = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=300, blank=True, default="")
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processed_payouts",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    _ALLOWED = {
        Status.PENDING: {Status.APPROVED, Status.REJECTED},
        Status.APPROVED: {Status.PAID, Status.REJECTED},
        Status.REJECTED: set(),
        Status.PAID: set(),
    }

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"{self.integrator} — {self.amount_uzs} UZS [{self.status}]"

    def can_transition(self, new_status: str) -> bool:
        return new_status in self._ALLOWED[PayoutRequest.Status(self.status)]
