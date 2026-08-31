"""§5 contract tests — literal CDR payload replay + error taxonomy."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.calls.models import CallAudio, CallRecord, Contact

from .conftest import DOC_API_KEY

pytestmark = pytest.mark.django_db

UPLOAD_URL = "/api/call/v1/upload"

# Valid Base64 with the OggS magic prefix, standing in for the contract's
# truncated "T2dnUwACAAAAAAAAAAA...==" example.
AUDIO_BYTES = b"OggS\x00\x02" + b"doocall-test-opus-payload" * 4
AUDIO_B64 = base64.b64encode(AUDIO_BYTES).decode()


def doc_payload(**overrides: Any) -> dict[str, Any]:
    """The §5.1 example CDR, replayed field-for-field."""
    payload: dict[str, Any] = {
        "user_name": "operator1",
        "api_key": DOC_API_KEY,
        "call_id": "a1b2c3-...",
        "call_type": "inbound",
        "call_status": "answered",
        "from": "+998901234567",
        "from_name": "Aziz Karimov",
        "to": "+998998887766",
        "to_name": "Jonibek Yorqulov",
        "operator_number": "+998998887766",
        "counterparty_number": "+998901234567",
        "counterparty_name": "Aziz Karimov",
        "sim_slot": 0,
        "duration": 47,
        "start_time": "2026-08-09 14:03:11",
        "end_time": "2026-08-09 14:03:58",
        "audio_filename": "998901234567_20260809140311.ogg",
        "audio_file": AUDIO_B64,
        "latitude": 41.311081,
        "longitude": 69.240562,
        "address": "",
    }
    payload.update(overrides)
    return payload


class TestUploadSuccess:
    def test_success_envelope_shape_is_exact(
        self,
        client: APIClient,
        operator: OperatorProfile,
        contact_aziz: Contact,
        fake_storage: dict[str, bytes],
    ) -> None:
        response = client.post(UPLOAD_URL, doc_payload(), format="json")

        assert response.status_code == 200
        body = response.json()
        # §5.4 — snapshot of the EXACT field set.
        assert set(body.keys()) == {
            "success",
            "status",
            "call_id",
            "server_id",
            "received_at",
            "resolved_name",
            "audio",
        }
        assert set(body["audio"].keys()) == {"stored", "url", "size_bytes"}

        assert body["success"] is True
        assert body["status"] == "received"
        assert body["call_id"] == "a1b2c3-..."
        assert body["server_id"].startswith("srv_")
        # ISO-8601 UTC with Z suffix, e.g. 2026-08-09T14:04:02Z.
        assert body["received_at"].endswith("Z") and "T" in body["received_at"]
        # Backend catalogue overrides the device-sent name (§5.4).
        assert body["resolved_name"] == "Aziz Karimov (Mijoz)"
        assert body["audio"] == {
            "stored": True,
            "url": f"https://minio.test/doocall-recordings/{operator.company_id}/a1b2c3-.../primary/998901234567_20260809140311.ogg?X-Amz-Signature=test",
            "size_bytes": len(AUDIO_BYTES),
        }

    def test_record_persisted_with_both_time_representations(
        self,
        client: APIClient,
        operator: OperatorProfile,
        fake_storage: dict[str, bytes],
    ) -> None:
        client.post(UPLOAD_URL, doc_payload(), format="json")

        record = CallRecord.all_objects.get(call_id="a1b2c3-...")
        # Device-local strings kept verbatim…
        assert record.start_time_local == "2026-08-09 14:03:11"
        assert record.end_time_local == "2026-08-09 14:03:58"
        # …and aware UTC datetimes stored (Tashkent is UTC+5).
        assert record.start_time.isoformat() == "2026-08-09T09:03:11+00:00"
        assert record.duration == 47
        assert record.counterparty_name == "Aziz Karimov"  # device name kept for audit
        assert record.operator_number == "+998998887766"
        audio = CallAudio.objects.get(call=record)
        assert audio.kind == CallAudio.Kind.PRIMARY
        assert fake_storage[audio.object_key] == AUDIO_BYTES

    def test_numbers_are_normalized_e164(
        self, client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
    ) -> None:
        client.post(
            UPLOAD_URL,
            doc_payload(
                call_id="norm-1",
                **{"from": "901234567"},  # 9 digits → +998
                to="998998887766",  # 12 digits → +
                operator_number="99 888-77-66",  # garbage separators, 9 digits
                counterparty_number="901234567",
            ),
            format="json",
        )
        record = CallRecord.all_objects.get(call_id="norm-1")
        assert record.from_number == "+998901234567"
        assert record.to_number == "+998998887766"
        assert record.operator_number == "+998998887766"
        assert record.counterparty_number == "+998901234567"

    def test_no_audio_upload(
        self, client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
    ) -> None:
        # §5.3: file not found → audio_filename="none", audio_file=null.
        response = client.post(
            UPLOAD_URL,
            doc_payload(call_id="noaudio-1", audio_filename="none", audio_file=None),
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["audio"] == {"stored": False, "url": None, "size_bytes": 0}
        assert not fake_storage

    def test_realtime_second_audio(
        self, client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
    ) -> None:
        # §5.3 recommended second pair.
        response = client.post(
            UPLOAD_URL,
            doc_payload(
                call_id="rt-1",
                audio_filename_realtime="realtime_998901234567_20260809140311.ogg",
                audio_file_realtime=AUDIO_B64,
            ),
            format="json",
        )
        assert response.status_code == 200
        record = CallRecord.all_objects.get(call_id="rt-1")
        kinds = set(CallAudio.objects.filter(call=record).values_list("kind", flat=True))
        assert kinds == {"primary", "realtime"}
        assert len(fake_storage) == 2


class TestUploadErrors:
    def test_duplicate_call_id_409_exact_body(
        self, client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
    ) -> None:
        assert client.post(UPLOAD_URL, doc_payload(), format="json").status_code == 200
        response = client.post(UPLOAD_URL, doc_payload(), format="json")

        assert response.status_code == 409
        body = response.json()
        # §5.4 duplicate envelope fields.
        assert body["success"] is False
        assert body["status"] == "already_exists"
        assert body["call_id"] == "a1b2c3-..."
        assert body["message"] == "call_id already exists"
        assert body["error_code"] == "DUPLICATE_CALL_ID"
        # No second row was created.
        assert CallRecord.all_objects.filter(call_id="a1b2c3-...").count() == 1

    def test_bad_api_key_401(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(UPLOAD_URL, doc_payload(api_key="not-a-key"), format="json")
        assert response.status_code == 401
        body = response.json()
        assert body == {
            "success": False,
            "message": "invalid api_key",
            "error_code": "INVALID_API_KEY",
        }

    def test_oversized_audio_413(
        self, client: APIClient, operator: OperatorProfile, settings: Any
    ) -> None:
        settings.AUDIO_MAX_MB = 0  # every non-empty payload is now oversized
        response = client.post(UPLOAD_URL, doc_payload(call_id="big-1"), format="json")

        assert response.status_code == 413
        body = response.json()
        assert body["error_code"] == "AUDIO_TOO_LARGE"
        assert body["status"] == "error"
        assert body["call_id"] == "big-1"
        # Size rejection must not leave a half-created CDR behind.
        assert not CallRecord.all_objects.filter(call_id="big-1").exists()

    def test_missing_field_400(self, client: APIClient, operator: OperatorProfile) -> None:
        payload = doc_payload()
        del payload["call_id"]
        response = client.post(UPLOAD_URL, payload, format="json")

        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert body["error_code"] == "MISSING_FIELD"
        assert "call_id" in body["message"]

    def test_invalid_base64_400(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            UPLOAD_URL, doc_payload(call_id="b64-1", audio_file="!!not-base64!!"), format="json"
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "MISSING_FIELD"

    def test_invalid_datetime_400(
        self, client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
    ) -> None:
        response = client.post(
            UPLOAD_URL, doc_payload(call_id="dt-1", start_time="09.08.2026 14:03"), format="json"
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "MISSING_FIELD"
