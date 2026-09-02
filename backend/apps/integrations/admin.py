from django.contrib import admin

from .models import CrmCatalogEntry, CrmIntegration


@admin.register(CrmIntegration)
class CrmIntegrationAdmin(admin.ModelAdmin):
    list_display = ("provider", "company", "is_enabled", "last_status", "last_delivery_at")
    list_filter = ("provider", "is_enabled", "last_status")


@admin.register(CrmCatalogEntry)
class CrmCatalogEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "site_url", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
