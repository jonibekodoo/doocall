from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from .models import AppLog, CallAudio, CallRecord, Contact, ContactPhone


class CallAudioInline(admin.TabularInline):
    model = CallAudio
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "filename", "object_key", "content_type", "size_bytes")


@admin.register(CallRecord)
class CallRecordAdmin(admin.ModelAdmin):
    """CDRs are immutable evidence — strictly read-only in the admin."""

    list_display = (
        "call_id",
        "company",
        "operator",
        "call_type",
        "call_status",
        "counterparty_number",
        "counterparty_name",
        "duration",
        "start_time",
    )
    list_filter = ("company", "call_type", "call_status")
    search_fields = ("call_id", "counterparty_number", "counterparty_name")
    date_hierarchy = "start_time"
    inlines = (CallAudioInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: CallRecord | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: CallRecord | None = None) -> bool:
        return False


class ContactPhoneInline(admin.TabularInline):
    model = ContactPhone
    extra = 1


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "created_at")
    list_filter = ("company",)
    search_fields = ("name", "phones__number")
    inlines = (ContactPhoneInline,)


@admin.register(AppLog)
class AppLogAdmin(admin.ModelAdmin):
    list_display = ("operator", "company", "hours", "created_at")
    list_filter = ("company",)
    readonly_fields = ("company", "operator", "hours", "log_text", "created_at")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
