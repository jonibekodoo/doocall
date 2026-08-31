"""Accounts: custom User, Role, OperatorProfile, Device, SimCard.

Terminology (backend-api-docs.md §3):
* ``User`` — web/admin identity (dashboard login).
* ``OperatorProfile.user_name`` — the device-app login identifier (NOT a
  phone number) used by every device API request together with ``api_key``.
* ``SimCard`` — per-SIM-slot real phone number; fills ``operator_number``
  on each uploaded CallRecord.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from apps.core.tenancy import TenantModel, get_current_company_id


def make_api_key() -> str:
    return uuid.uuid4().hex


class Role(models.Model):
    """Named permission set within a company (``company``=NULL → platform role)."""

    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    name = models.CharField(max_length=80)
    permissions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of permission codes, e.g. ['calls.view', 'billing.manage']",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uniq_role_per_company",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.company or 'platform'})"


class TenantUserManager(UserManager["User"]):
    """User manager that also honours the tenant context."""

    def get_queryset(self) -> models.QuerySet[User]:
        qs = super().get_queryset()
        company_id = get_current_company_id()
        if company_id is not None:
            qs = qs.filter(company_id=company_id)
        return qs


class User(AbstractUser):
    """Custom AUTH_USER_MODEL. ``company``=NULL → platform superuser/staff."""

    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="users",
    )
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    phone = models.CharField(max_length=20, blank=True)
    email_verified = models.BooleanField(default=False)
    is_company_admin = models.BooleanField(
        default=False, help_text="Company-level admin (cabinet settings, deletes)"
    )

    objects = UserManager()  # type: ignore[misc,assignment]  # global — auth needs unscoped
    tenant_objects = TenantUserManager()  # tenant-scoped access for app code

    def __str__(self) -> str:
        return self.get_username()


class OperatorGroup(TenantModel):
    """Cabinet-defined operator group (department/team)."""

    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_group_per_company"),
        ]

    def __str__(self) -> str:
        return self.name


class OperatorProfile(TenantModel):
    """Device-app identity of an operator (login name + permanent api_key)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="operator_profile")
    group = models.ForeignKey(
        OperatorGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="operators"
    )
    user_name = models.CharField(max_length=150, help_text="Device login identifier")
    api_key = models.CharField(max_length=64, unique=True, default=make_api_key)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user_name"], name="uniq_operator_username_per_company"
            ),
        ]

    def __str__(self) -> str:
        return self.user_name


class Device(TenantModel):
    """Android device attached to an operator (Login §4 ``device`` block)."""

    operator = models.ForeignKey(OperatorProfile, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=64, help_text="Settings.Secure.ANDROID_ID")
    model = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    os_version = models.CharField(max_length=20, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["operator", "device_id"], name="uniq_device_per_operator"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.model} ({self.device_id[:8]}…)"


class SimCard(TenantModel):
    """Real phone number per SIM slot (§3 ``phone_numbers`` array)."""

    operator = models.ForeignKey(
        OperatorProfile, on_delete=models.CASCADE, related_name="sim_cards"
    )
    sim_slot = models.SmallIntegerField(help_text="0/1; -1 = undetected")
    number = models.CharField(max_length=20, help_text="E.164, normalized")
    is_active = models.BooleanField(default=True)
    recording_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["operator", "sim_slot"], name="uniq_sim_slot_per_operator"
            ),
        ]

    def __str__(self) -> str:
        return f"slot {self.sim_slot}: {self.number}"
