"""Request serializers for /api/call/v1 — field names mirror the contract 1:1.

Validation failures surface as 400 MISSING_FIELD via the exception handler,
so every ``required=True`` here IS the contract's required-field list.
"""

from __future__ import annotations

from rest_framework import serializers


class PhoneNumberEntrySerializer(serializers.Serializer):
    sim_slot = serializers.IntegerField()
    number = serializers.CharField()


class DeviceInfoSerializer(serializers.Serializer):
    device_id = serializers.CharField()
    model = serializers.CharField(required=False, allow_blank=True, default="")
    manufacturer = serializers.CharField(required=False, allow_blank=True, default="")
    app_version = serializers.CharField(required=False, allow_blank=True, default="")
    os_version = serializers.CharField(required=False, allow_blank=True, default="")


class AuthRequestSerializer(serializers.Serializer):
    """§4 — minimal legacy payload + optional SaaS extensions."""

    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
    server = serializers.CharField(required=False, allow_blank=True, default="")
    phone_numbers = PhoneNumberEntrySerializer(many=True, required=False, default=list)
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    device = DeviceInfoSerializer(required=False, allow_null=True, default=None)


class UploadRequestSerializer(serializers.Serializer):
    """§5.1 — full CDR. api_key/user_name validated separately (auth layer)."""

    user_name = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")

    call_id = serializers.CharField()
    call_type = serializers.ChoiceField(choices=["inbound", "outbound", "internal"])
    call_status = serializers.ChoiceField(choices=["answered", "no_answer", "busy", "failed"])

    from_number = serializers.CharField(source="from", required=False)  # placeholder, see below
    to = serializers.CharField()
    from_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    to_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    operator_number = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    operator_number_missing = serializers.BooleanField(required=False, default=False)
    counterparty_number = serializers.CharField()
    counterparty_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    sim_slot = serializers.IntegerField(required=False, default=-1)

    duration = serializers.IntegerField(min_value=0)
    start_time = serializers.CharField()  # "yyyy-MM-dd HH:mm:ss" device-local
    end_time = serializers.CharField(required=False, allow_blank=True, default="")

    audio_filename = serializers.CharField(required=False, allow_blank=True, default="none")
    audio_file = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    audio_filename_realtime = serializers.CharField(required=False, allow_blank=True, default="")
    audio_file_realtime = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, default="")

    def get_fields(self) -> dict[str, serializers.Field]:
        # "from" is a Python keyword — declare it dynamically.
        fields = super().get_fields()
        del fields["from_number"]
        fields["from"] = serializers.CharField()
        return fields


class CallsListRequestSerializer(serializers.Serializer):
    """§6 — dedup pre-check."""

    user_name = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")
    call_ids = serializers.ListField(child=serializers.CharField(), allow_empty=True)


class StatsRequestSerializer(serializers.Serializer):
    """§7 — operator stats (auth fields only)."""

    user_name = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")


class LogRequestSerializer(serializers.Serializer):
    """§8 — diagnostic log upload."""

    user_name = serializers.CharField(required=False, allow_blank=True, default="")
    api_key = serializers.CharField(required=False, allow_blank=True, default="")
    hours = serializers.IntegerField(required=False, min_value=1, default=24)
    log_text = serializers.CharField(allow_blank=False)
