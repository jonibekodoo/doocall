"""Billing: PricingSetting (history-tracked), Subscription, Invoice, Payment."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models, transaction

from apps.core.tenancy import TenantModel


class PricingSetting(models.Model):
    """Current pricing knobs. ``company``=NULL → the single global default row.

    History-tracked: every value change appends a :class:`PricingSettingHistory`
    row (see :meth:`save`) — the admin edits this model directly and the trail
    is preserved automatically.
    """

    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="pricing_settings",
    )
    price_per_operator_uzs = models.PositiveIntegerField()
    trial_days = models.PositiveSmallIntegerField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                name="uniq_pricing_per_company",
                nulls_distinct=False,  # at most ONE global default row
            ),
        ]

    def __str__(self) -> str:
        scope = self.company or "global"
        return f"{scope}: {self.price_per_operator_uzs} UZS/operator, trial {self.trial_days}d"

    _TRACKED_FIELDS = ("price_per_operator_uzs", "trial_days")

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Append a history row on create and on every tracked-value change."""
        old: PricingSetting | None = None
        if self.pk:
            old = PricingSetting.objects.filter(pk=self.pk).first()

        changed = old is None or any(
            getattr(old, f) != getattr(self, f) for f in self._TRACKED_FIELDS
        )

        with transaction.atomic():
            super().save(*args, **kwargs)
            if changed:
                PricingSettingHistory.objects.create(
                    setting=self,
                    price_per_operator_uzs=self.price_per_operator_uzs,
                    trial_days=self.trial_days,
                    changed_by=self.updated_by,
                )
            # Tariff change → in-app notice to every affected client profile.
            if old is not None and old.price_per_operator_uzs != self.price_per_operator_uzs:
                from apps.companies.models import Company

                affected = (
                    [self.company]
                    if self.company is not None
                    else list(Company.objects.exclude(status=Company.Status.SUSPENDED))
                )
                message = (
                    f"Tarif o'zgardi: {self.price_per_operator_uzs:,} UZS / operator / oy "
                    f"(avvalgisi {old.price_per_operator_uzs:,} UZS). "
                    "Yangi tarif shu kundan boshlab qo'llanadi."
                ).replace(",", " ")
                BillingNotification.all_objects.bulk_create(
                    BillingNotification(
                        company=company,
                        kind=BillingNotification.Kind.TARIFF_CHANGED,
                        message=message,
                        amount_uzs=self.price_per_operator_uzs,
                    )
                    for company in affected
                )


class PricingSettingHistory(models.Model):
    """Append-only snapshot written on every PricingSetting change."""

    setting = models.ForeignKey(PricingSetting, on_delete=models.CASCADE, related_name="history")
    price_per_operator_uzs = models.PositiveIntegerField()
    trial_days = models.PositiveSmallIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name_plural = "pricing setting histories"

    def __str__(self) -> str:
        return f"{self.price_per_operator_uzs} UZS @ {self.changed_at:%Y-%m-%d %H:%M}"


class Subscription(TenantModel):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL)
    price_per_operator_uzs = models.PositiveIntegerField(
        help_text="Snapshot of the pricing at subscription time"
    )
    operator_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["company"], name="uniq_subscription_per_company"),
        ]

    def __str__(self) -> str:
        return f"{self.company} — {self.status}"


def make_invoice_number() -> str:
    return f"INV-{uuid.uuid4().hex[:10].upper()}"


class Invoice(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"

    subscription = models.ForeignKey(
        Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    number = models.CharField(max_length=30, unique=True, default=make_invoice_number)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    total_uzs = models.PositiveBigIntegerField(default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status", "-created_at"])]

    def __str__(self) -> str:
        return self.number


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=300)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_uzs = models.PositiveBigIntegerField()
    amount_uzs = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return self.description


class DailyCharge(TenantModel):
    """One operator-day of usage (the unit of the daily billing model).

    ``operator_name`` survives operator deletion — an operator added and
    removed the same day still costs one day.
    """

    date = models.DateField()
    operator = models.ForeignKey(
        "accounts.OperatorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_charges",
    )
    operator_name = models.CharField(max_length=150)
    amount_uzs = models.PositiveIntegerField()
    price_per_operator_uzs = models.PositiveIntegerField(
        help_text="Monthly tariff in force on that day (rate = tariff / days in month)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-date", "operator_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "date", "operator_name"],
                name="uniq_daily_charge_per_operator_day",
            ),
        ]
        indexes = [models.Index(fields=["company", "-date"])]

    def __str__(self) -> str:
        return f"{self.date} {self.operator_name}: {self.amount_uzs} UZS"


class MonthlyStatement(TenantModel):
    """Previous-month usage total, settled from the balance on the 1st."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    month = models.DateField(help_text="First day of the billed month")
    total_uzs = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["company", "month"], name="uniq_statement_per_month"),
        ]

    def __str__(self) -> str:
        return f"{self.company} {self.month:%Y-%m}: {self.total_uzs} UZS ({self.status})"


class BillingNotification(TenantModel):
    """In-app message shown in the client's cabinet (bell + profile)."""

    class Kind(models.TextChoices):
        CHARGE_SETTLED = "charge_settled", "Monthly charge deducted"
        PAYMENT_DUE = "payment_due", "Payment due"
        PAYMENT_REQUESTED = "payment_requested", "Payment request submitted"
        PAYMENT_RECEIVED = "payment_received", "Payment received"
        TARIFF_CHANGED = "tariff_changed", "Tariff changed"
        BLOCKED = "blocked", "Access blocked"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.CharField(max_length=300)
    amount_uzs = models.BigIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.kind}: {self.message[:40]}"


class Payment(TenantModel):
    class Provider(models.TextChoices):
        PAYME = "payme", "Payme"
        CLICK = "click", "Click"
        MANUAL = "manual", "Bank / Naqd"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    provider = models.CharField(max_length=10, choices=Provider.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount_uzs = models.PositiveBigIntegerField()
    external_id = models.CharField(max_length=128, blank=True, help_text="Gateway txn id")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_payments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.provider} {self.amount_uzs} UZS ({self.status})"
