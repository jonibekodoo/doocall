from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Append-only trail — read-only in the admin."""

    list_display = ("action", "company", "actor", "target_model", "target_id", "created_at")
    list_filter = ("action", "company")
    search_fields = ("action", "target_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: AuditLog | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: AuditLog | None = None) -> bool:
        return False
