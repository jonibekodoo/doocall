"""Tenant root: Company."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone


class Company(models.Model):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    # Account-wide cabinet toggles (§6.5): contact_import / recording / pin.
    feature_flags = models.JSONField(default=dict, blank=True)
    # Company-level integration API key (cabinet-rotatable; NOT operator keys).
    api_key = models.CharField(max_length=64, blank=True, default="")
    # Audio retention override (days); NULL → global AUDIO_RETENTION_DAYS.
    audio_retention_days = models.PositiveSmallIntegerField(null=True, blank=True)
    # Locale: device-local timestamps are parsed and reports/day-boundaries
    # computed in THIS zone (multi-country tenants).
    country = models.CharField(
        max_length=2, blank=True, default="UZ", help_text="ISO 3166-1 alpha-2"
    )
    timezone = models.CharField(max_length=64, blank=True, default="Asia/Tashkent")

    # ── Integrator binding (Addendum A.2) ──────────────────────────────────
    class AcquiredVia(models.TextChoices):
        SELF_SIGNUP = "self_signup", "Self signup"
        REFERRAL_LINK = "referral_link", "Referral link"
        INTEGRATOR_MANUAL = "integrator_manual", "Registered by integrator"

    integrator = models.ForeignKey(
        "partners.Integrator",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="companies",
    )
    acquired_via = models.CharField(
        max_length=20, choices=AcquiredVia.choices, default=AcquiredVia.SELF_SIGNUP
    )
    # Outbound webhook: signed POST on every new call.
    webhook_url = models.URLField(blank=True, default="")
    webhook_secret = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name

    # Integrator binding is immutable except via the explicit superadmin
    # reassignment service (partners.services.reassign_integrator).
    _allow_integrator_change = False

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and not self._allow_integrator_change:
            old = Company.objects.filter(pk=self.pk).values("integrator_id", "acquired_via").first()
            if old and (
                old["integrator_id"] != self.integrator_id
                or old["acquired_via"] != self.acquired_via
            ):
                raise ValueError("integrator binding is immutable; use reassign_integrator()")
        super().save(*args, **kwargs)

    @property
    def is_on_trial(self) -> bool:
        return (
            self.status == self.Status.TRIAL
            and self.trial_ends_at is not None
            and self.trial_ends_at >= timezone.now()
        )
