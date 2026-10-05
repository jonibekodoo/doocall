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
ROLE_SALES_MANAGER = "sales_manager"
PLATFORM_ROLES = (
    ROLE_SUPERADMIN,
    ROLE_PLATFORM_ADMIN,
    ROLE_INTEGRATOR,
    ROLE_SALES_MANAGER,
)

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
SALES_MANAGER_PERMS = ["sales.portal"]


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
    company_name = models.CharField(max_length=200, blank=True, help_text="Integrator's company / brand")
    logo_key = models.CharField(max_length=500, blank=True, default="", help_text="MinIO key")
    is_public = models.BooleanField(
        default=False, help_text="Show in the public 'our integrators' landing section"
    )
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    referral_code = models.CharField(max_length=12, unique=True, default=_referral_code)
    # NULL → use PlatformSetting.default_cashback_percent.
    cashback_percent_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    # Payout destination (card / bank requisites) — free-form per A.2.
    payout_details = models.JSONField(default=dict, blank=True)
    # Structured bank requisites (shown to admin for manual bank payout).
    bank_card = models.CharField(max_length=32, blank=True, default="")
    bank_mfo = models.CharField(max_length=16, blank=True, default="")
    bank_inn = models.CharField(max_length=16, blank=True, default="")
    bank_transit = models.CharField(max_length=32, blank=True, default="")
    # The sales manager who recruited/owns this integrator (earns a commission).
    sales_manager = models.ForeignKey(
        "partners.SalesManager",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="integrators",
    )
    # Public offer acceptance.
    offer_accepted_version = models.PositiveIntegerField(default=0)
    offer_accepted_at = models.DateTimeField(null=True, blank=True)
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


class IntegratorApplication(models.Model):
    """A public 'become an integrator' request left from the landing page."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True)
    company = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    sales_manager = models.ForeignKey(
        "partners.SalesManager",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.phone}) [{self.status}]"




class SalesManager(models.Model):
    """A sales manager recruits/owns integrators and earns a commission on the
    payments of those integrators' companies — a second tier above cashback."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sales_manager_profile"
    )
    name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True)
    logo_key = models.CharField(max_length=500, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # Commission percent of each payment (independent of the integrator cashback).
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    payout_details = models.JSONField(default=dict, blank=True)
    bank_card = models.CharField(max_length=32, blank=True, default="")
    bank_mfo = models.CharField(max_length=16, blank=True, default="")
    bank_inn = models.CharField(max_length=16, blank=True, default="")
    bank_transit = models.CharField(max_length=32, blank=True, default="")
    offer_accepted_version = models.PositiveIntegerField(default=0)
    offer_accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.commission_percent}%)"

    @property
    def effective_percent(self) -> Decimal:
        return Decimal(str(self.commission_percent))

    @property
    def balance_uzs(self) -> int:
        accrued = (
            self.commissions.filter(status=SalesCommission.Status.ACCRUED).aggregate(
                s=models.Sum("amount_uzs")
            )["s"]
            or 0
        )
        held = (
            self.payout_requests.filter(
                status__in=[SalesPayoutRequest.Status.PENDING, SalesPayoutRequest.Status.APPROVED]
            ).aggregate(s=models.Sum("amount_uzs"))["s"]
            or 0
        )
        return int(accrued) - int(held)


class SalesCommission(models.Model):
    """One commission per successful payment for the linked sales manager."""

    class Status(models.TextChoices):
        ACCRUED = "accrued", "Accrued"
        REVERSED = "reversed", "Reversed (refund)"
        PAID_OUT = "paid_out", "Paid out"

    payment = models.OneToOneField(
        "billing.Payment", on_delete=models.CASCADE, related_name="sales_commission"
    )
    sales_manager = models.ForeignKey(
        SalesManager, on_delete=models.CASCADE, related_name="commissions"
    )
    integrator = models.ForeignKey(
        Integrator, on_delete=models.CASCADE, related_name="sales_commissions"
    )
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="sales_commissions"
    )
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    amount_uzs = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACCRUED)
    payout = models.ForeignKey(
        "partners.SalesPayoutRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="allocated_commissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sales_manager", "status", "-created_at"]),
            models.Index(fields=["company", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.amount_uzs} UZS ({self.percent}%) [{self.status}]"


class SalesPayoutRequest(models.Model):
    """Sales manager withdrawal request — pending → approved → paid | rejected."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    sales_manager = models.ForeignKey(
        SalesManager, on_delete=models.CASCADE, related_name="payout_requests"
    )
    amount_uzs = models.PositiveBigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=300, blank=True, default="")
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processed_sales_payouts",
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
        return f"{self.sales_manager} — {self.amount_uzs} UZS [{self.status}]"

    def can_transition(self, new_status: str) -> bool:
        return new_status in self._ALLOWED[SalesPayoutRequest.Status(self.status)]


class OfferDocument(models.Model):
    """Singleton public-offer document shown in profiles; version bumps on edit.

    ``content`` is the Uzbek text (the default language); ``content_ru`` /
    ``content_en`` hold the translations — see ``localized_content``."""

    content = models.TextField(blank=True, default="")
    content_ru = models.TextField(blank=True, default="")
    content_en = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"offer v{self.version}"


DOC_LANGS = ("uz", "ru", "en")


def doc_field(lang: str) -> str:
    """Model field holding a document's text in ``lang`` (uz is the base)."""
    return "content" if lang == "uz" else f"content_{lang}"


def localized_content(doc: "OfferDocument | LegalDocument", lang: str) -> str:
    """Text in the requested language, falling back to the first non-empty
    translation (uz → ru → en) so a page is never blank just because one
    language has not been filled in yet."""
    for candidate in (lang, *DOC_LANGS):
        if candidate in DOC_LANGS:
            value = getattr(doc, doc_field(candidate), "")
            if value:
                return value
    return ""


def doc_contents(doc: "OfferDocument | LegalDocument") -> dict[str, str]:
    return {lang: getattr(doc, doc_field(lang)) for lang in DOC_LANGS}


def get_offer_document() -> "OfferDocument":
    row = OfferDocument.objects.first()
    if row is None:
        row = OfferDocument(content="", version=1)
        row.save()
    return row


class LegalDocument(models.Model):
    """Public legal pages required by card acquirers (Visa/Mastercard):
    privacy policy, terms & conditions, refund/cancellation policy.
    Admin-edited sanitised HTML, one row per kind, version bumps on edit."""

    class Kind(models.TextChoices):
        PRIVACY = "privacy", "Privacy policy"
        TERMS = "terms", "Terms & conditions"
        REFUND = "refund", "Refund / cancellation policy"

    kind = models.CharField(max_length=16, choices=Kind.choices, unique=True)
    content = models.TextField(blank=True, default="")  # Uzbek (default language)
    content_ru = models.TextField(blank=True, default="")
    content_en = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.kind} v{self.version}"


LEGAL_KINDS = frozenset(k for k, _ in LegalDocument.Kind.choices)


def get_legal_document(kind: str) -> "LegalDocument":
    row, _ = LegalDocument.objects.get_or_create(kind=kind)
    return row


class PlatformNotification(models.Model):
    """User-scoped in-app notification (integrators / sales managers).

    Distinct from the company-scoped billing.BillingNotification."""

    class Kind(models.TextChoices):
        PAYOUT_STATUS = "payout_status", "Payout status"
        LEAD_ASSIGNED = "lead_assigned", "Lead assigned"
        BALANCE_WARNING = "balance_warning", "Balance warning"
        COMMISSION = "commission", "Commission accrued"
        GENERIC = "generic", "Generic"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="platform_notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERIC)
    message = models.CharField(max_length=300)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} → {self.user_id}: {self.message[:40]}"


# ── CRM (Phase 2): funnels / leads / tasks per sales manager ────────────────
DEFAULT_STAGES = [
    ("Yangi", "#d99a2b"),
    ("Aloqa", "#2a9691"),
    ("Taklif", "#1f7873"),
    ("Muzokara", "#1c605d"),
    ("Yutildi", "#3fb27a"),
    ("Yutqazildi", "#e05d47"),
]


class Pipeline(models.Model):
    """A global sales funnel — managed by the platform admin, shared by all
    sales managers. (``sales_manager`` kept nullable for legacy rows.)"""

    sales_manager = models.ForeignKey(
        SalesManager, on_delete=models.CASCADE, related_name="pipelines", null=True, blank=True
    )
    name = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class PipelineStage(models.Model):
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(default=0)
    color = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Lead(models.Model):
    """A CRM card moving through a pipeline's stages."""

    sales_manager = models.ForeignKey(SalesManager, on_delete=models.CASCADE, related_name="leads")
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="leads")
    stage = models.ForeignKey(PipelineStage, on_delete=models.SET_NULL, null=True, related_name="leads")
    application = models.ForeignKey(
        IntegratorApplication,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leads",
    )
    full_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    company = models.CharField(max_length=200, blank=True)
    source = models.ForeignKey(
        "partners.LeadSource", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    tags = models.ManyToManyField("partners.LeadTag", blank=True, related_name="leads")
    priority = models.PositiveSmallIntegerField(default=0, help_text="0-3 stars")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["sales_manager", "pipeline", "stage"])]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.phone})"


class CrmTask(models.Model):
    sales_manager = models.ForeignKey(SalesManager, on_delete=models.CASCADE, related_name="tasks")
    lead = models.ForeignKey(
        Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks"
    )
    type = models.ForeignKey(
        "partners.CrmTaskType", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    title = models.CharField(max_length=300)
    due_at = models.DateTimeField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    cancel_reason = models.CharField(max_length=300, blank=True, default="")
    auto = models.BooleanField(default=False, help_text="System-generated (e.g. balance warning)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_done", "due_at", "-created_at"]
        indexes = [models.Index(fields=["sales_manager", "is_done", "due_at"])]

    def __str__(self) -> str:
        return f"{self.title} [{'done' if self.is_done else 'open'}]"


class LeadEvent(models.Model):
    """Timeline entry shown in a lead's chatter (amoCRM-style)."""

    class Kind(models.TextChoices):
        CREATED = "created", "Created"
        NOTE = "note", "Note"
        STAGE = "stage", "Stage change"
        TASK = "task", "Task"
        TASK_DONE = "task_done", "Task done"
        TASK_CANCELLED = "cancelled", "Task cancelled"
        FIELD = "field", "Field change"
        ASSIGNED = "assigned", "Assigned"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    task = models.ForeignKey(
        "partners.CrmTask", null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["lead", "created_at"])]

    def __str__(self) -> str:
        return f"{self.kind} @ {self.lead_id}"


def ensure_global_pipelines() -> Pipeline:
    """Seed the single global default funnel + stages (admin-managed)."""
    pipe = Pipeline.objects.filter(sales_manager__isnull=True).order_by("order", "id").first()
    if pipe is not None:
        return pipe
    pipe = Pipeline.objects.create(sales_manager=None, name="Asosiy varonka", order=0)
    for idx, (label, color) in enumerate(DEFAULT_STAGES):
        PipelineStage.objects.create(pipeline=pipe, name=label, order=idx, color=color)
    return pipe


# Backwards-compatible alias used in a couple of call sites.
def ensure_default_pipeline(manager: "SalesManager | None" = None) -> Pipeline:
    return ensure_global_pipelines()


class LeadSource(models.Model):
    """Admin-managed lead source (Manba) — selectable on leads."""

    name = models.CharField(max_length=120, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class LeadTag(models.Model):
    """Admin-managed lead tag (Teg) — selectable on leads."""

    name = models.CharField(max_length=80, unique=True)
    color = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


DEFAULT_SOURCES = ["Ariza", "Qo'ng'iroq", "Telegram", "Instagram", "Tavsiya", "Veb-sayt"]


def seed_lead_sources() -> None:
    if LeadSource.objects.exists():
        return
    for i, name in enumerate(DEFAULT_SOURCES):
        LeadSource.objects.create(name=name, order=i)


class CrmTaskType(models.Model):
    """Admin-managed task type (name + icon key), selectable when creating a task."""

    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=32, blank=True, default="", help_text="lucide icon key")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


# (name, icon key understood by the frontend)
DEFAULT_TASK_TYPES = [
    ("Qo'ng'iroq", "phone"),
    ("Uchrashuv", "calendar"),
    ("Xabar", "message"),
    ("Eslatma", "bell"),
    ("Boshqa", "clipboard"),
]


def seed_task_types() -> None:
    if CrmTaskType.objects.exists():
        return
    for i, (name, icon) in enumerate(DEFAULT_TASK_TYPES):
        CrmTaskType.objects.create(name=name, icon=icon, order=i)
