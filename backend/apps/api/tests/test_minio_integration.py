"""Integration: audio really lands in MinIO and the returned URL streams.

Runs against the compose MinIO; skips cleanly when it is unreachable
(e.g. bare-metal pytest without the stack).
"""

from __future__ import annotations

import base64
import urllib.request

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.api import storage

from .conftest import DOC_API_KEY

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

UPLOAD_URL = "/api/call/v1/upload"
AUDIO_BYTES = b"OggS\x00\x02doocall-minio-integration-payload"


def minio_available() -> bool:
    try:
        storage.client().bucket_exists(settings.MINIO_BUCKET)
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False
    return True


@pytest.fixture(autouse=True)
def _require_minio() -> None:
    if not minio_available():
        pytest.skip("MinIO not reachable in this environment")


def test_audio_roundtrip_through_minio(client: APIClient, operator: OperatorProfile) -> None:
    call_id = "minio-int-1"
    response = client.post(
        UPLOAD_URL,
        {
            "user_name": "operator1",
            "api_key": DOC_API_KEY,
            "call_id": call_id,
            "call_type": "outbound",
            "call_status": "answered",
            "from": "+998998887766",
            "to": "+998901234567",
            "counterparty_number": "+998901234567",
            "duration": 5,
            "start_time": "2026-08-14 10:00:00",
            "audio_filename": "minio_int.ogg",
            "audio_file": base64.b64encode(AUDIO_BYTES).decode(),
        },
        format="json",
    )

    assert response.status_code == 200
    audio = response.json()["audio"]
    assert audio["stored"] is True
    assert audio["size_bytes"] == len(AUDIO_BYTES)

    # 1. Object exists in the bucket with the exact bytes.
    object_key = f"{operator.company_id}/{call_id}/primary/minio_int.ogg"
    obj = storage.client().get_object(settings.MINIO_BUCKET, object_key)
    try:
        assert obj.read() == AUDIO_BYTES
    finally:
        obj.close()
        obj.release_conn()

    # 2. The presigned URL from the response actually streams the audio.
    with urllib.request.urlopen(audio["url"], timeout=10) as stream:  # noqa: S310
        assert stream.status == 200
        assert stream.read() == AUDIO_BYTES

    # Cleanup so reruns start fresh.
    storage.client().remove_object(settings.MINIO_BUCKET, object_key)
