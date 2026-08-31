"""Core models — platform-wide audit trail."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of privileged/admin actions.

    ``company`` is nullable: platform-level actions (pricing changes, company
    suspension) may not belong to a tenant.
    """

    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id} @ {self.created_at:%Y-%m-%d %H:%M}"


class AppRelease(models.Model):
    """Mobile APK build uploaded from the admin portal.

    The newest row is what the landing "download app" button serves;
    the binary itself lives in MinIO under ``object_key``.
    """

    version = models.CharField(max_length=32, unique=True)
    object_key = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    notes = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="app_releases",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"APK {self.version} ({self.size_bytes} B)"
