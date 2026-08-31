from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.core.models import AuditLog

from .models import (
    Invoice,
    InvoiceLine,
    Payment,
    PricingSetting,
    PricingSettingHistory,
    Subscription,
)


class PricingSettingHistoryInline(admin.TabularInline):
    model = PricingSettingHistory
    extra = 0
    can_delete = False
    readonly_fields = ("price_per_operator_uzs", "trial_days", "changed_by", "changed_at")

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(PricingSetting)
class PricingSettingAdmin(admin.ModelAdmin):
    """Editable — every change automatically appends a history row."""

    list_display = ("company", "price_per_operator_uzs", "trial_days", "updated_at")
    inlines = (PricingSettingHistoryInline,)

    def save_model(
        self, request: HttpRequest, obj: PricingSetting, form: object, change: bool
    ) -> None:
        obj.updated_by = cast("Any", request.user)  # history rows record who changed it
        super().save_model(request, obj, form, change)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "status", "price_per_operator_uzs", "trial_ends_at")
    list_filter = ("status",)


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "company", "status", "total_uzs", "issued_at", "due_at")
    list_filter = ("status", "company")
    search_fields = ("number",)
    inlines = (InvoiceLineInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("company", "provider", "amount_uzs", "status", "created_at", "approved_by")
    list_filter = ("provider", "status", "company")
    actions = ("approve_payments", "reject_payments")
    readonly_fields = ("approved_by", "approved_at")

    @admin.action(description="Approve selected payments (manual)")
    def approve_payments(self, request: HttpRequest, queryset: QuerySet[Payment]) -> None:
        # Full provider lifecycle: invoice paid + company (re)activated +
        # period extended + AuditLog — one code path shared with webhooks.
        from apps.billing import services

        pending = queryset.filter(status=Payment.Status.PENDING)
        count = 0
        for payment in pending:
            services.apply_payment(payment, actor=cast("Any", request.user))
            AuditLog.objects.create(
                company=payment.company,
                actor=cast("Any", request.user),
                action="payment.approve",
                target_model="billing.Payment",
                target_id=str(payment.pk),
                changes={"amount_uzs": payment.amount_uzs, "provider": payment.provider},
            )
            count += 1
        skipped = queryset.count() - count
        msg = f"Approved {count} payment(s)."
        if skipped:
            msg += f" Skipped {skipped} non-pending."
        self.message_user(request, msg, messages.SUCCESS if count else messages.WARNING)

    @admin.action(description="Reject selected payments")
    def reject_payments(self, request: HttpRequest, queryset: QuerySet[Payment]) -> None:
        updated = queryset.filter(status=Payment.Status.PENDING).update(
            status=Payment.Status.REJECTED
        )
        self.message_user(request, f"Rejected {updated} payment(s).", messages.WARNING)
