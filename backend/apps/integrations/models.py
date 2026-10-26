"""Per-company CRM integrations (amoCRM / Bitrix24 / Odoo / Kotib Analytics).

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
        KOTIB = "kotib", "Kotib Analytics"

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


class CrmDelivery(TenantModel):
    """One attempt to push one call into one CRM — the per-call audit trail
    behind "which calls reached amoCRM?". Written by the dispatcher (and by
    manual retries); never updated, a retry is a new row."""

    class Status(models.TextChoices):
        OK = "ok", "ok"
        ERROR = "error", "error"

    call = models.ForeignKey(
        "calls.CallRecord", on_delete=models.CASCADE, related_name="crm_deliveries"
    )
    provider = models.CharField(max_length=20, choices=CrmIntegration.Provider.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.CharField(max_length=500, blank=True, default="")
    is_retry = models.BooleanField(default=False)
    # CRM-side id of the delivered call (Bitrix24: telephony CALL_ID) — lets a
    # recording that arrives later be attached to the same call.
    external_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["company", "provider", "-created_at"], name="crm_deliv_prov_idx"),
            models.Index(fields=["call", "provider"], name="crm_deliv_call_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} call={self.call_id} {self.status}"


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


class CallAnalysis(TenantModel):
    """Kotib AI analysis of one call (``analysis.completed`` webhook).

    One row per Kotib ``audio_data_id`` per company — re-sends overwrite it
    (latest wins). ``call`` is our matched CallRecord (phone + start time);
    it stays NULL until a re-send finds it. Kotib's ``audio_file_url`` needs
    the Kotib API key, so it is deliberately not stored."""

    call = models.ForeignKey(
        "calls.CallRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_analyses",
    )
    audio_data_id = models.BigIntegerField()
    audio_file_id = models.BigIntegerField(null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    final_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    conversation_text = models.TextField(blank=True, default="")
    # [{key, name, score, comment (sanitized HTML), is_violation}]
    prompt_scores = models.JSONField(default=list, blank=True)
    client_phone = models.CharField(max_length=32, blank=True, default="")
    client_summary = models.TextField(blank=True, default="")
    # [{key, name, value (any JSON)}]
    client_answers = models.JSONField(default=list, blank=True)
    has_violation = models.BooleanField(default=False)
    signature_verified = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["company", "audio_data_id"], name="uniq_analysis_per_company"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "-start_time"], name="call_analysis_start_idx"),
            models.Index(fields=["company", "call"], name="call_analysis_call_idx"),
        ]

    def __str__(self) -> str:
        return f"analysis {self.audio_data_id} ({self.company_id})"
