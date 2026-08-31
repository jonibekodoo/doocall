from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Device, OperatorProfile, Role, SimCard, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "company", "role", "is_staff", "is_active")
    list_filter = ("company", "is_staff", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (  # type: ignore[operator]
        ("dooCall", {"fields": ("company", "role", "phone")}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "created_at")
    list_filter = ("company",)


class SimCardInline(admin.TabularInline):
    model = SimCard
    extra = 0


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 0
    readonly_fields = ("last_seen_at",)


@admin.register(OperatorProfile)
class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ("user_name", "full_name", "company", "is_active", "created_at")
    list_filter = ("company", "is_active")
    search_fields = ("user_name", "full_name")
    readonly_fields = ("api_key",)
    inlines = (SimCardInline, DeviceInline)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "operator", "manufacturer", "model", "last_seen_at")
    list_filter = ("company", "manufacturer")
    search_fields = ("device_id",)


@admin.register(SimCard)
class SimCardAdmin(admin.ModelAdmin):
    list_display = ("number", "sim_slot", "operator", "is_active")
    list_filter = ("company", "sim_slot")
    search_fields = ("number",)
