"""Calls: CallRecord (full CDR contract §5.1), CallAudio, Contact, AppLog."""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.tenancy import TenantModel


class CallRecord(TenantModel):
    """One CDR row — every field of the upload contract (§5.1/§5.2).

    Dedup key: UNIQUE (company, call_id). ``server_id`` is the public id
    returned to devices (§5.4).
    """

    class CallType(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"
        INTERNAL = "internal", "Internal"  # planned in the contract

    class CallStatus(models.TextChoices):
        ANSWERED = "answered", "Answered"
        NO_ANSWER = "no_answer", "No answer"
        BUSY = "busy", "Busy"  # planned
        FAILED = "failed", "Failed"  # planned

    # Identity
    call_id = models.CharField(max_length=128)
    server_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    operator = models.ForeignKey(
        "accounts.OperatorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="call_records",
    )
    device = models.ForeignKey(
        "accounts.Device",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="call_records",
    )

    # Direction / outcome
    call_type = models.CharField(max_length=10, choices=CallType.choices)
    call_status = models.CharField(max_length=10, choices=CallStatus.choices)

    # Both parties — full E.164 numbers + names (§0.1, §0.2, §5.2)
    from_number = models.CharField(max_length=20)
    from_name = models.CharField(max_length=200, null=True, blank=True)
    to_number = models.CharField(max_length=20)
    to_name = models.CharField(max_length=200, null=True, blank=True)
    operator_number = models.CharField(max_length=20, null=True, blank=True)
    operator_number_missing = models.BooleanField(default=False)
    counterparty_number = models.CharField(max_length=20)
    counterparty_name = models.CharField(max_length=200, null=True, blank=True)
    resolved_name = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Backend contact-catalog override (§5.4), kept separate for audit",
    )
    sim_slot = models.SmallIntegerField(default=-1)

    # Time / duration
    duration = models.PositiveIntegerField(help_text="seconds")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    # Raw device-local strings exactly as uploaded ("yyyy-MM-dd HH:mm:ss",
    # device timezone, §1) — kept verbatim for audit alongside the aware UTC.
    start_time_local = models.CharField(max_length=19, blank=True)
    end_time_local = models.CharField(max_length=19, blank=True)

    # Location
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=500, blank=True)

    # Server-side bookkeeping
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        constraints = [
            # THE dedup rule of the whole contract (§1).
            models.UniqueConstraint(fields=["company", "call_id"], name="uniq_call_id_per_company"),
        ]
        indexes = [
            # Composite indexes (master spec §13 placeholders — the obvious
            # dashboard/report access paths).
            models.Index(fields=["company", "-start_time"]),
            models.Index(fields=["company", "operator", "-start_time"]),
            models.Index(fields=["company", "counterparty_number"]),
            models.Index(fields=["company", "call_type", "call_status"]),
        ]
        ordering = ["-start_time"]

    def __str__(self) -> str:
        return f"{self.call_type} {self.counterparty_number} ({self.call_status})"


class CallAudio(models.Model):
    """Stored audio for a call. Two kinds per §5.3: primary + realtime."""

    class Kind(models.TextChoices):
        PRIMARY = "primary", "Primary (phone recording)"
        REALTIME = "realtime", "Realtime (microphone)"

    call = models.ForeignKey(CallRecord, on_delete=models.CASCADE, related_name="audios")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PRIMARY)
    filename = models.CharField(max_length=255)
    object_key = models.CharField(max_length=500, help_text="MinIO object key")
    content_type = models.CharField(max_length=100, default="audio/ogg")
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["call", "kind"], name="uniq_audio_kind_per_call"),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.filename}"


class Contact(TenantModel):
    """Company contact catalog — source of ``resolved_name`` (§5.4)."""

    name = models.CharField(max_length=200)
    note = models.CharField(max_length=500, blank=True)
    responsible = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="responsible_contacts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ContactPhone(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="phones")
    number = models.CharField(max_length=20, help_text="E.164, normalized")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contact", "number"], name="uniq_phone_per_contact"),
        ]
        indexes = [models.Index(fields=["number"])]

    def __str__(self) -> str:
        return self.number


class AppLog(TenantModel):
    """Device diagnostic log upload (§8) — NOT a call log."""

    operator = models.ForeignKey(
        "accounts.OperatorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="app_logs",
    )
    hours = models.PositiveSmallIntegerField(default=24)
    log_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "-created_at"])]

    def __str__(self) -> str:
        return f"log from {self.operator} @ {self.created_at:%Y-%m-%d %H:%M}"
