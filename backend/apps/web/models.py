"""Web-cabinet persistence: per-user column prefs + export jobs."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.tenancy import TenantModel

DEFAULT_CALL_COLUMNS = [
    "start_time",
    "direction",
    "status",
    "operator",
    "counterparty",
    "duration",
    "audio",
]


class CallColumnPreference(models.Model):
    """Which columns a cabinet user shows in the calls table."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="call_columns"
    )
    columns = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"columns for {self.user_id}"


class ExportJob(TenantModel):
    """Async CSV/XLSX export of the (filtered) calls list."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="export_jobs"
    )
    format = models.CharField(max_length=5, choices=Format.choices, default=Format.CSV)
    filters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    object_key = models.CharField(max_length=500, blank=True, default="")
    row_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"export {self.pk} ({self.status})"
