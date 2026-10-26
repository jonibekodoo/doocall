"""Remote Dial: the cabinet asks an operator's phone (open WebSocket) to
place an outgoing call. One DialCommand per "Call" click — its UUID is the
command_id the phone echoes in every ack/status frame."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.core.tenancy import TenantModel


class DialCommand(TenantModel):
    class Status(models.TextChoices):
        SENT = "sent", "Sent to the device"
        RECEIVED = "received", "Device accepted"
        REJECTED = "rejected", "Device rejected"
        DIALING = "dialing", "Dialing"
        ACTIVE = "active", "Connected"
        DISCONNECTED = "disconnected", "Ended"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "No ack within 30 s"
        OFFLINE = "offline", "Device offline (not sent)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # command_id
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    operator = models.ForeignKey(
        "accounts.OperatorProfile",
        null=True,
        on_delete=models.SET_NULL,
        related_name="dial_commands",
    )
    device_id = models.CharField(max_length=64)
    number = models.CharField(max_length=20, help_text="E.164")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SENT)
    reject_reason = models.CharField(max_length=32, blank=True, default="")
    sim_mode = models.CharField(max_length=16, blank=True, default="")
    used_sim_slot = models.SmallIntegerField(null=True, blank=True)
    duration_sec = models.PositiveIntegerField(null=True, blank=True)
    cause = models.CharField(max_length=16, blank=True, default="")
    # Client retry dedupe (same user + key within 60 s → same command).
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    # Bitrix24 click-to-call (ONEXTERNALCALLSTART): Bitrix already registered
    # this call — the later CDR delivery finishes/attaches to it instead of
    # registering a new one (b24_used_at marks that it was consumed).
    source = models.CharField(max_length=16, blank=True, default="cabinet")
    b24_call_id = models.CharField(max_length=64, blank=True, default="")
    b24_user_id = models.CharField(max_length=16, blank=True, default="")
    b24_entity_type = models.CharField(max_length=16, blank=True, default="")
    b24_entity_id = models.CharField(max_length=32, blank=True, default="")
    b24_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantModel.Meta):
        indexes = [
            models.Index(fields=["company", "-created_at"], name="dial_company_created_idx"),
            models.Index(fields=["company", "device_id", "-created_at"], name="dial_device_idx"),
            models.Index(fields=["company", "b24_call_id"], name="dial_b24_call_idx"),
        ]

    def __str__(self) -> str:
        return f"dial {self.id} → {self.device_id} ({self.status})"
