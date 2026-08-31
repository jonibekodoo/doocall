"""Companies admin — status/trial/operator-count columns + lifecycle actions."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.contrib import admin, messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.core.models import AuditLog

from .models import Company

# Branding for the whole admin (served at app.admin.doocall.local).
admin.site.site_header = "dooCall Admin"
admin.site.site_title = "dooCall Admin"
admin.site.index_title = "Platform administration"

TRIAL_EXTENSION_DAYS = 7


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "trial_ends_at", "operator_count", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    actions = ("suspend_companies", "activate_companies", "extend_trial")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Company]:
        qs = (
            super()
            .get_queryset(request)
            .annotate(_operator_count=Count("accounts_operatorprofile_set", distinct=True))
        )
        return cast(QuerySet[Company], qs)

    @admin.display(description="Operators", ordering="_operator_count")
    def operator_count(self, obj: Any) -> int:
        return cast(int, obj._operator_count)

    def _audit(self, request: HttpRequest, action: str, companies: QuerySet[Company]) -> None:
        AuditLog.objects.bulk_create(
            AuditLog(
                company=c,
                actor=cast("Any", request.user),
                action=action,
                target_model="companies.Company",
                target_id=str(c.pk),
            )
            for c in companies
        )

    @admin.action(description="Suspend selected companies")
    def suspend_companies(self, request: HttpRequest, queryset: QuerySet[Company]) -> None:
        updated = queryset.update(status=Company.Status.SUSPENDED)
        self._audit(request, "company.suspend", queryset)
        self.message_user(request, f"Suspended {updated} company(ies).", messages.WARNING)

    @admin.action(description="Activate selected companies")
    def activate_companies(self, request: HttpRequest, queryset: QuerySet[Company]) -> None:
        updated = queryset.update(status=Company.Status.ACTIVE)
        self._audit(request, "company.activate", queryset)
        self.message_user(request, f"Activated {updated} company(ies).", messages.SUCCESS)

    @admin.action(description=f"Extend trial by {TRIAL_EXTENSION_DAYS} days")
    def extend_trial(self, request: HttpRequest, queryset: QuerySet[Company]) -> None:
        now = timezone.now()
        for company in queryset:
            base = company.trial_ends_at or now
            company.trial_ends_at = max(base, now) + timedelta(days=TRIAL_EXTENSION_DAYS)
            company.status = Company.Status.TRIAL
            company.save(update_fields=["trial_ends_at", "status", "updated_at"])
        self._audit(request, "company.extend_trial", queryset)
        self.message_user(
            request,
            f"Extended trial for {queryset.count()} company(ies) by {TRIAL_EXTENSION_DAYS} days.",
            messages.SUCCESS,
        )
