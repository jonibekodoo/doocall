"""Per-company CRM integrations (amoCRM / Bitrix24 / Odoo).

The "custom" integration (signed webhook + public API) lives on the Company
model itself (``webhook_url``/``webhook_secret``/``api_key``) — this model
covers only the ready-made CRM connectors configured from the cabinet.
"""

from __future__ import annotations

from django.db import models

from apps.core.tenancy import TenantModel


class CrmIntegration(TenantModel):
    class Provider(models.TextChoices):
        AMOCRM = "amocrm", "amoCRM / Kommo"
        BITRIX24 = "bitrix24", "Bitrix24"
        ODOO = "odoo", "Odoo"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    is_enabled = models.BooleanField(default=False)
    # Provider-specific credentials/settings; secret values are masked on read.
    config = models.JSONField(default=dict, blank=True)

    last_status = models.CharField(max_length=10, blank=True, default="")  # ok | error
    last_error = models.CharField(max_length=500, blank=True, default="")
    last_delivery_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["company", "provider"], name="uniq_integration_per_company"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider} ({self.company})"


class CrmCatalogEntry(models.Model):
    """Platform-wide CRM tile shown in every cabinet's integration grid.

    Managed from the admin portal; a tile is just a logo linking to the
    CRM's own site (moizvonki-style grid). The special connectors
    (amoCRM/Bitrix24/Odoo) are hardcoded tiles rendered before these.
    """

    name = models.CharField(max_length=100, unique=True)
    site_url = models.URLField()
    logo_key = models.CharField(max_length=500, blank=True, default="", help_text="MinIO key")
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "CRM catalog entries"

    def __str__(self) -> str:
        return self.name
