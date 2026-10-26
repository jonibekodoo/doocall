"""Late audio: re-uploading an existing call_id that has NO audio attaches
the recording (200 audio_attached); everything else stays the 409."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.api.tests.conftest import DOC_PASSWORD
from apps.calls.models import CallAudio, CallRecord
from apps.companies.models import Company
from apps.integrations.models import CrmIntegration

from .test_upload_contract import AUDIO_B64, AUDIO_BYTES, UPLOAD_URL, doc_payload

pytestmark = pytest.mark.django_db

DUPLICATE = {
    "success": False,
    "status": "already_exists",
    "call_id": "late-1",
    "message": "call_id already exists",
    "error_code": "DUPLICATE_CALL_ID",
}


def _first_without_audio(client: APIClient, call_id: str = "late-1") -> Any:
    return client.post(
        UPLOAD_URL,
        doc_payload(call_id=call_id, audio_filename="none", audio_file=None),
        format="json",
    )


def test_late_audio_is_attached(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    assert _first_without_audio(client).status_code == 200
    record = CallRecord.all_objects.get(call_id="late-1")
    before = {f.name: getattr(record, f.name) for f in CallRecord._meta.fields}

    response = client.post(
        UPLOAD_URL,
        doc_payload(call_id="late-1", duration=999, counterparty_number="+998900000000"),
        format="json",
    )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "server_id": f"srv_{record.server_id.hex}",
        "audio_attached": True,
    }
    audio = CallAudio.objects.get(call=record)
    assert audio.kind == "primary" and audio.content_type == "audio/ogg"
    assert fake_storage[audio.object_key] == AUDIO_BYTES
    record.refresh_from_db()
    # No other call field changes (duration/number in the re-upload ignored).
    assert {f.name: getattr(record, f.name) for f in CallRecord._meta.fields} == before


def test_late_realtime_audio_only(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    _first_without_audio(client)
    response = client.post(
        UPLOAD_URL,
        doc_payload(
            call_id="late-1",
            audio_filename="none",
            audio_file=None,
            audio_filename_realtime="mic.m4a",
            audio_file_realtime=AUDIO_B64,
        ),
        format="json",
    )
    assert response.json()["audio_attached"] is True
    assert CallAudio.objects.get().kind == "realtime"


def test_second_late_upload_is_409(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    _first_without_audio(client)
    assert client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json").status_code == 200
    again = client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    assert again.status_code == 409 and again.json() == DUPLICATE
    assert CallAudio.objects.count() == 1


def test_reupload_without_audio_is_409(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    _first_without_audio(client)
    response = _first_without_audio(client)
    assert response.status_code == 409 and response.json() == DUPLICATE


def test_call_uploaded_with_audio_stays_409(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    response = client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    assert response.status_code == 409 and response.json() == DUPLICATE


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [("audio_file", "!!!not-base64!!!", 400)],
)
def test_late_audio_is_validated_like_a_new_upload(
    client: APIClient,
    operator: OperatorProfile,
    fake_storage: dict[str, bytes],
    field: str,
    value: str,
    code: int,
) -> None:
    _first_without_audio(client)
    response = client.post(
        UPLOAD_URL, doc_payload(call_id="late-1", **{field: value}), format="json"
    )
    assert response.status_code == code
    assert not CallAudio.objects.exists()


def test_late_audio_too_large_413(
    client: APIClient,
    operator: OperatorProfile,
    fake_storage: dict[str, bytes],
    settings: Any,
) -> None:
    _first_without_audio(client)
    settings.AUDIO_MAX_MB = 0
    response = client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    assert response.status_code == 413
    assert not CallAudio.objects.exists()


def test_other_operator_cannot_attach(
    client: APIClient,
    operator: OperatorProfile,
    company: Company,
    fake_storage: dict[str, bytes],
) -> None:
    _first_without_audio(client)
    user = User.objects.create_user(username="op2@acme", password=DOC_PASSWORD, company=company)
    other = OperatorProfile.all_objects.create(
        company=company, user=user, user_name="operator2", api_key="k" * 32
    )
    response = client.post(
        UPLOAD_URL,
        doc_payload(call_id="late-1", user_name=other.user_name, api_key=other.api_key),
        format="json",
    )
    assert response.status_code == 409
    assert not CallAudio.objects.exists()


def test_other_company_call_id_is_a_new_call(
    client: APIClient, operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    other = Company.objects.create(name="Other", slug="other-co", status=Company.Status.ACTIVE)
    foreign = CallRecord.all_objects.create(
        company=other,
        call_id="late-1",
        call_type="inbound",
        call_status="answered",
        from_number="+998901234567",
        to_number="+998998887766",
        counterparty_number="+998901234567",
        duration=5,
        start_time="2026-08-09T09:03:11Z",
    )
    response = client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    assert response.status_code == 200 and response.json()["status"] == "received"
    assert not CallAudio.objects.filter(call=foreign).exists()  # no cross-tenant write
    assert CallRecord.all_objects.filter(call_id="late-1").count() == 2


def test_bitrix24_late_attach_enqueued_after_commit(
    client: APIClient,
    operator: OperatorProfile,
    company: Company,
    fake_storage: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    from apps.api import views

    enqueued: list[int] = []
    monkeypatch.setattr(views, "_enqueue_late_audio", enqueued.append)
    monkeypatch.setattr(views, "_enqueue_crm_dispatch", lambda record_id: None)
    _first_without_audio(client)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
    assert enqueued == []  # no Bitrix24 integration → nothing to do

    CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": "https://acme.bitrix24.ru/rest/1/x/"},
    )
    with django_capture_on_commit_callbacks(execute=True):
        _first_without_audio(client, call_id="late-2")
    with django_capture_on_commit_callbacks(execute=True):
        client.post(UPLOAD_URL, doc_payload(call_id="late-2"), format="json")
    assert enqueued == [CallRecord.all_objects.get(call_id="late-2").pk]


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("rec.ogg", "audio/ogg"),
        ("REC.OGG", "audio/ogg"),
        ("rec.m4a", "audio/mp4"),
        ("rec.mp3", "audio/mpeg"),
        ("rec.wav", "audio/wav"),
        ("rec.amr", "audio/amr"),
        ("rec", "application/octet-stream"),
        ("rec.zzz-unknown", "application/octet-stream"),
    ],
)
def test_content_type_from_filename(
    client: APIClient,
    operator: OperatorProfile,
    fake_storage: dict[str, bytes],
    filename: str,
    content_type: str,
) -> None:
    client.post(
        UPLOAD_URL, doc_payload(call_id=f"ct-{filename}", audio_filename=filename), format="json"
    )
    assert CallAudio.objects.get(call__call_id=f"ct-{filename}").content_type == content_type


@pytest.mark.django_db(transaction=True)
def test_concurrent_late_uploads_attach_once(
    operator: OperatorProfile, fake_storage: dict[str, bytes]
) -> None:
    APIClient().post(
        UPLOAD_URL,
        doc_payload(call_id="late-1", audio_filename="none", audio_file=None),
        format="json",
    )
    codes: list[int] = []
    barrier = threading.Barrier(3)

    def upload() -> None:
        barrier.wait()
        try:
            codes.append(
                APIClient()
                .post(UPLOAD_URL, doc_payload(call_id="late-1"), format="json")
                .status_code
            )
        finally:
            connection.close()

    threads = [threading.Thread(target=upload) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [200, 409, 409]
    assert CallAudio.objects.count() == 1
